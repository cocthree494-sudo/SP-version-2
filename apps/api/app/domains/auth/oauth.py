"""Provider-neutral OAuth/OIDC helpers for social authentication.

The module owns only the authorization-code exchange and profile validation.
User/tenant creation and account-linking policy remain in the auth service so
social identities cannot bypass the existing tenant boundary.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol, cast
from urllib.parse import urlencode

import httpx
import jwt
from jwt.exceptions import InvalidTokenError

from app.core.config import settings

SocialProvider = Literal["google", "microsoft", "github"]
OAuthMode = Literal["login", "register", "link"]


class OAuthError(RuntimeError):
    """Base class for expected OAuth flow failures."""


class OAuthProviderDisabledError(OAuthError):
    """Raised when a provider is not completely configured."""


class OAuthStateError(OAuthError):
    """Raised for an invalid, expired, or replayed authorization state."""


class OAuthExchangeError(OAuthError):
    """Raised when an authorization code or provider profile is invalid."""


@dataclass(frozen=True, slots=True)
class OAuthProviderConfig:
    provider: SocialProvider
    client_id: str | None
    client_secret: str | None
    authorize_url: str
    token_url: str
    userinfo_url: str
    issuer: str | None
    jwks_url: str | None
    scope: str

    @property
    def enabled(self) -> bool:
        return bool(self.client_id and self.client_secret)

    @property
    def oidc(self) -> bool:
        # Microsoft uses a tenant-specific issuer when the ``common`` endpoint
        # is configured, so it is validated by ``_valid_microsoft_issuer``
        # rather than by this static config value.  It is still an OIDC flow
        # and must receive/validate a nonce and an ID token.
        return self.provider in {"google", "microsoft"}


@dataclass(frozen=True, slots=True)
class OAuthProfile:
    provider: SocialProvider
    issuer: str
    subject: str
    email: str
    email_verified: bool
    display_name: str | None


@dataclass(frozen=True, slots=True)
class OAuthState:
    provider: SocialProvider
    mode: OAuthMode
    code_verifier: str
    nonce: str
    redirect_uri: str
    user_id: str | None = None
    tenant_id: str | None = None
    organization_slug: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "provider": self.provider,
            "mode": self.mode,
            "code_verifier": self.code_verifier,
            "nonce": self.nonce,
            "redirect_uri": self.redirect_uri,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "organization_slug": self.organization_slug,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> OAuthState:
        provider = value.get("provider")
        mode = value.get("mode")
        required = ("code_verifier", "nonce", "redirect_uri")
        if provider not in {"google", "microsoft", "github"} or mode not in {
            "login",
            "register",
            "link",
        }:
            raise OAuthStateError("Invalid OAuth state")
        if any(not isinstance(value.get(key), str) for key in required):
            raise OAuthStateError("Invalid OAuth state")
        return cls(
            provider=cast(SocialProvider, provider),
            mode=cast(OAuthMode, mode),
            code_verifier=cast(str, value["code_verifier"]),
            nonce=cast(str, value["nonce"]),
            redirect_uri=cast(str, value["redirect_uri"]),
            user_id=value.get("user_id") if isinstance(value.get("user_id"), str) else None,
            tenant_id=value.get("tenant_id") if isinstance(value.get("tenant_id"), str) else None,
            organization_slug=(
                value.get("organization_slug")
                if isinstance(value.get("organization_slug"), str)
                else None
            ),
        )


class OAuthStateStore(Protocol):
    async def put(self, state: str, value: OAuthState, ttl_seconds: int) -> None: ...

    async def consume(self, state: str) -> OAuthState | None: ...


@dataclass(frozen=True, slots=True)
class SocialContinuation:
    """One-time handoff from a verified provider to an app-owned next step."""

    kind: Literal["register", "select", "link"]
    profile: OAuthProfile
    user_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "user_id": self.user_id,
            "profile": {
                "provider": self.profile.provider,
                "issuer": self.profile.issuer,
                "subject": self.profile.subject,
                "email": self.profile.email,
                "email_verified": self.profile.email_verified,
                "display_name": self.profile.display_name,
            },
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> SocialContinuation:
        kind = value.get("kind")
        profile_value = value.get("profile")
        if kind not in {"register", "select", "link"} or not isinstance(profile_value, dict):
            raise OAuthStateError("Invalid social continuation")
        required = ("provider", "issuer", "subject", "email", "email_verified")
        if any(key not in profile_value for key in required):
            raise OAuthStateError("Invalid social continuation")
        provider = profile_value.get("provider")
        if provider not in {"google", "microsoft", "github"}:
            raise OAuthStateError("Invalid social continuation")
        if not all(
            isinstance(profile_value.get(key), str)
            for key in ("issuer", "subject", "email")
        ):
            raise OAuthStateError("Invalid social continuation")
        return cls(
            kind=cast(Literal["register", "select", "link"], kind),
            user_id=value.get("user_id") if isinstance(value.get("user_id"), str) else None,
            profile=OAuthProfile(
                provider=cast(SocialProvider, provider),
                issuer=cast(str, profile_value["issuer"]),
                subject=cast(str, profile_value["subject"]),
                email=cast(str, profile_value["email"]),
                email_verified=profile_value["email_verified"] is True,
                display_name=(
                    profile_value.get("display_name")
                    if isinstance(profile_value.get("display_name"), str)
                    else None
                ),
            ),
        )


class SocialContinuationStore(Protocol):
    async def put_continuation(
        self,
        token: str,
        value: SocialContinuation,
        ttl_seconds: int,
    ) -> None: ...

    async def consume_continuation(self, token: str) -> SocialContinuation | None: ...


class RedisOAuthStateStore:
    """One-time state storage backed by the shared Redis deployment."""

    def __init__(self, redis: Any) -> None:
        self.redis = redis

    @staticmethod
    def _key(state: str) -> str:
        digest = hashlib.sha256(state.encode("ascii")).hexdigest()
        return f"support-agent:oauth-state:{digest}"

    async def put(self, state: str, value: OAuthState, ttl_seconds: int) -> None:
        await self.redis.set(
            self._key(state),
            json.dumps(value.as_dict(), separators=(",", ":")),
            ex=ttl_seconds,
        )

    async def consume(self, state: str) -> OAuthState | None:
        raw = await self.redis.getdel(self._key(state))
        if raw is None:
            return None
        try:
            decoded = json.loads(raw)
            if not isinstance(decoded, dict):
                raise ValueError
            return OAuthState.from_dict(decoded)
        except (TypeError, ValueError, json.JSONDecodeError, OAuthStateError) as exc:
            raise OAuthStateError("Invalid OAuth state") from exc

    @staticmethod
    def _continuation_key(token: str) -> str:
        digest = hashlib.sha256(token.encode("ascii")).hexdigest()
        return f"support-agent:social-continuation:{digest}"

    async def put_continuation(
        self,
        token: str,
        value: SocialContinuation,
        ttl_seconds: int,
    ) -> None:
        await self.redis.set(
            self._continuation_key(token),
            json.dumps(value.as_dict(), separators=(",", ":")),
            ex=ttl_seconds,
        )

    async def consume_continuation(self, token: str) -> SocialContinuation | None:
        raw = await self.redis.getdel(self._continuation_key(token))
        if raw is None:
            return None
        try:
            decoded = json.loads(raw)
            if not isinstance(decoded, dict):
                raise ValueError
            return SocialContinuation.from_dict(decoded)
        except (TypeError, ValueError, json.JSONDecodeError, OAuthStateError) as exc:
            raise OAuthStateError("Invalid social continuation") from exc


class InMemoryOAuthStateStore:
    """Deterministic test store; production always uses Redis."""

    def __init__(self) -> None:
        self._values: dict[str, tuple[OAuthState, float]] = {}
        self._continuations: dict[str, tuple[SocialContinuation, float]] = {}

    async def put(self, state: str, value: OAuthState, ttl_seconds: int) -> None:
        self._values[state] = (value, datetime.now(UTC).timestamp() + ttl_seconds)

    async def consume(self, state: str) -> OAuthState | None:
        stored = self._values.pop(state, None)
        if stored is None:
            return None
        value, expires_at = stored
        if datetime.now(UTC).timestamp() >= expires_at:
            return None
        return value

    async def put_continuation(
        self,
        token: str,
        value: SocialContinuation,
        ttl_seconds: int,
    ) -> None:
        self._continuations[token] = (
            value,
            datetime.now(UTC).timestamp() + ttl_seconds,
        )

    async def consume_continuation(self, token: str) -> SocialContinuation | None:
        stored = self._continuations.pop(token, None)
        if stored is None:
            return None
        value, expires_at = stored
        if datetime.now(UTC).timestamp() >= expires_at:
            return None
        return value


def _provider_config(provider: SocialProvider) -> OAuthProviderConfig:
    if provider == "google":
        return OAuthProviderConfig(
            provider=provider,
            client_id=settings.OAUTH_GOOGLE_CLIENT_ID,
            client_secret=(
                settings.OAUTH_GOOGLE_CLIENT_SECRET.get_secret_value()
                if settings.OAUTH_GOOGLE_CLIENT_SECRET
                else None
            ),
            authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",  # noqa: S106 - URL, not a credential
            userinfo_url="https://openidconnect.googleapis.com/v1/userinfo",
            issuer="https://accounts.google.com",
            jwks_url="https://www.googleapis.com/oauth2/v3/certs",
            scope="openid email profile",
        )
    if provider == "microsoft":
        tenant = settings.OAUTH_MICROSOFT_TENANT_ID.strip() or "common"
        return OAuthProviderConfig(
            provider=provider,
            client_id=settings.OAUTH_MICROSOFT_CLIENT_ID,
            client_secret=(
                settings.OAUTH_MICROSOFT_CLIENT_SECRET.get_secret_value()
                if settings.OAUTH_MICROSOFT_CLIENT_SECRET
                else None
            ),
            authorize_url=(
                f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
            ),
            token_url=f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
            userinfo_url="https://graph.microsoft.com/oidc/userinfo",
            issuer=None,
            jwks_url="https://login.microsoftonline.com/common/discovery/v2.0/keys",
            scope="openid profile email User.Read",
        )
    return OAuthProviderConfig(
        provider=provider,
        client_id=settings.OAUTH_GITHUB_CLIENT_ID,
        client_secret=(
            settings.OAUTH_GITHUB_CLIENT_SECRET.get_secret_value()
            if settings.OAUTH_GITHUB_CLIENT_SECRET
            else None
        ),
        authorize_url="https://github.com/login/oauth/authorize",
        token_url="https://github.com/login/oauth/access_token",  # noqa: S106 - URL, not a credential
        userinfo_url="https://api.github.com/user",
        issuer="https://github.com",
        jwks_url=None,
        scope="read:user user:email",
    )


def provider_config(provider: str) -> OAuthProviderConfig:
    if provider not in {"google", "microsoft", "github"}:
        raise OAuthProviderDisabledError("This sign-in provider is not available")
    config = _provider_config(cast(SocialProvider, provider))
    if not config.enabled:
        raise OAuthProviderDisabledError("This sign-in provider is not configured")
    return config


def redirect_uri(provider: SocialProvider, *, admin: bool = False) -> str:
    base_url = (
        settings.OAUTH_ADMIN_WEB_BASE_URL
        if admin and settings.OAUTH_ADMIN_WEB_BASE_URL
        else settings.OAUTH_WEB_BASE_URL
    )
    return f"{base_url.rstrip('/')}/api/auth/oauth/{provider}/callback"


def allowed_redirect_uris(provider: SocialProvider) -> frozenset[str]:
    return frozenset({redirect_uri(provider), redirect_uri(provider, admin=True)})


def build_authorization_request(
    provider: SocialProvider,
    *,
    mode: OAuthMode,
    redirect: str,
    user_id: str | None = None,
    tenant_id: str | None = None,
    organization_slug: str | None = None,
) -> tuple[str, str, OAuthState]:
    config = provider_config(provider)
    if redirect not in allowed_redirect_uris(provider):
        raise OAuthStateError("OAuth redirect URI is not configured for this application")
    if mode == "link" and (user_id is None or tenant_id is None):
        raise OAuthStateError("Authenticated account linking is required")

    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    nonce = secrets.token_urlsafe(32)
    oauth_state = OAuthState(
        provider=provider,
        mode=mode,
        code_verifier=code_verifier,
        nonce=nonce,
        redirect_uri=redirect,
        user_id=user_id,
        tenant_id=tenant_id,
        organization_slug=organization_slug,
    )
    params = {
        "response_type": "code",
        "client_id": config.client_id or "",
        "redirect_uri": redirect,
        "scope": config.scope,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    if config.oidc:
        params["nonce"] = nonce
    if provider == "github":
        params["allow_signup"] = "false"
    return f"{config.authorize_url}?{urlencode(params)}", state, oauth_state


async def exchange_code(
    provider: SocialProvider,
    *,
    code: str,
    oauth_state: OAuthState,
) -> OAuthProfile:
    config = provider_config(provider)
    if (
        oauth_state.provider != provider
        or oauth_state.redirect_uri not in allowed_redirect_uris(provider)
    ):
        raise OAuthStateError("OAuth state does not match the callback")
    if not code or len(code) > 4096:
        raise OAuthExchangeError("The provider returned an invalid authorization code")

    timeout = httpx.Timeout(settings.OAUTH_HTTP_TIMEOUT_SECONDS)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        try:
            token_response = await client.post(
                config.token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": oauth_state.redirect_uri,
                    "client_id": config.client_id,
                    "client_secret": config.client_secret,
                    "code_verifier": oauth_state.code_verifier,
                },
                headers={"Accept": "application/json"},
            )
            token_response.raise_for_status()
            token_payload = token_response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise OAuthExchangeError("The provider token exchange failed") from exc

        if not isinstance(token_payload, dict):
            raise OAuthExchangeError("The provider returned an invalid token response")
        access_token = token_payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise OAuthExchangeError("The provider returned no access token")

        if config.oidc:
            return await _oidc_profile(client, config, token_payload, oauth_state.nonce)
        return await _github_profile(client, config, access_token)


async def _oidc_profile(
    client: httpx.AsyncClient,
    config: OAuthProviderConfig,
    token_payload: dict[str, Any],
    expected_nonce: str,
) -> OAuthProfile:
    raw_id_token = token_payload.get("id_token")
    if not isinstance(raw_id_token, str) or not raw_id_token:
        raise OAuthExchangeError("The provider returned no identity token")
    if config.jwks_url is None:
        raise OAuthExchangeError("The provider identity configuration is incomplete")
    try:
        header = jwt.get_unverified_header(raw_id_token)
        kid = header.get("kid")
        algorithm = header.get("alg")
        if not isinstance(kid, str) or algorithm not in {"RS256", "RS384", "RS512"}:
            raise InvalidTokenError("Unsupported identity token header")
        jwks_response = await client.get(config.jwks_url)
        jwks_response.raise_for_status()
        keys = jwks_response.json().get("keys")
        if not isinstance(keys, list):
            raise InvalidTokenError("Invalid provider key set")
        jwk = next(
            (item for item in keys if isinstance(item, dict) and item.get("kid") == kid),
            None,
        )
        if jwk is None:
            raise InvalidTokenError("Provider signing key was not found")
        signing_key = jwt.PyJWK.from_json(json.dumps(jwk))
        claims = jwt.decode(
            raw_id_token,
            signing_key.key,
            algorithms=[algorithm],
            audience=config.client_id,
            options={"require": ["exp", "iat", "iss", "sub", "nonce"]},
        )
    except (InvalidTokenError, KeyError, TypeError, ValueError, httpx.HTTPError) as exc:
        raise OAuthExchangeError("The provider identity token could not be validated") from exc

    issuer = claims.get("iss")
    subject = claims.get("sub")
    nonce = claims.get("nonce")
    if not isinstance(issuer, str) or not isinstance(subject, str) or nonce != expected_nonce:
        raise OAuthExchangeError("The provider identity token did not match the login request")
    if config.provider == "google" and issuer != config.issuer:
        raise OAuthExchangeError("The provider issuer is invalid")
    if config.provider == "microsoft" and not _valid_microsoft_issuer(issuer):
        raise OAuthExchangeError("The provider issuer is invalid")

    email = claims.get("email")
    if not isinstance(email, str) or "@" not in email:
        raise OAuthExchangeError("The provider did not return a usable email")
    email_verified = claims.get("email_verified")
    if config.provider == "google" and email_verified is not True:
        raise OAuthExchangeError("The provider email is not verified")
    return OAuthProfile(
        provider=config.provider,
        issuer=issuer,
        subject=subject,
        email=email,
        email_verified=True if config.provider == "microsoft" else bool(email_verified),
        display_name=_display_name(claims),
    )


def _valid_microsoft_issuer(issuer: str) -> bool:
    prefix = "https://login.microsoftonline.com/"
    return issuer.startswith(prefix) and issuer.endswith("/v2.0") and len(issuer) > len(prefix) + 5


async def _github_profile(
    client: httpx.AsyncClient,
    config: OAuthProviderConfig,
    access_token: str,
) -> OAuthProfile:
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {access_token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        response = await client.get(config.userinfo_url, headers=headers)
        response.raise_for_status()
        profile = response.json()
        email_response = await client.get("https://api.github.com/user/emails", headers=headers)
        email_response.raise_for_status()
        email_items = email_response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise OAuthExchangeError("The GitHub identity request failed") from exc
    if not isinstance(profile, dict) or not isinstance(profile.get("id"), (int, str)):
        raise OAuthExchangeError("GitHub returned an invalid identity")
    if not isinstance(email_items, list):
        raise OAuthExchangeError("GitHub returned no email identities")
    verified = [
        item
        for item in email_items
        if (
            isinstance(item, dict)
            and item.get("verified") is True
            and isinstance(item.get("email"), str)
        )
    ]
    selected = next((item for item in verified if item.get("primary") is True), None)
    selected = selected or (verified[0] if verified else None)
    if selected is None:
        raise OAuthExchangeError("GitHub did not return a verified email")
    subject = str(profile["id"])
    return OAuthProfile(
        provider=config.provider,
        issuer=config.issuer or "https://github.com",
        subject=subject,
        email=cast(str, selected["email"]),
        email_verified=True,
        display_name=(
            profile.get("name") if isinstance(profile.get("name"), str) else profile.get("login")
        ),
    )


def _display_name(claims: dict[str, Any]) -> str | None:
    for key in ("name", "given_name", "preferred_username"):
        value = claims.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


__all__ = [
    "InMemoryOAuthStateStore",
    "OAuthError",
    "OAuthExchangeError",
    "OAuthMode",
    "OAuthProfile",
    "OAuthProviderDisabledError",
    "OAuthState",
    "OAuthStateError",
    "OAuthStateStore",
    "RedisOAuthStateStore",
    "SocialContinuation",
    "SocialContinuationStore",
    "SocialProvider",
    "build_authorization_request",
    "exchange_code",
    "provider_config",
    "redirect_uri",
]
