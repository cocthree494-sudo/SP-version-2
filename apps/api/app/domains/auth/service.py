"""Transactional authentication workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from anyio import to_thread
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    dummy_password_hash,
    generate_refresh_token,
    get_refresh_token_tenant_id,
    hash_password,
    hash_refresh_token,
    password_needs_rehash,
    verify_password,
)
from app.core.tenancy import tenant_session_scope
from app.domains.auth.oauth import (
    OAuthProfile,
    OAuthProviderDisabledError,
    OAuthStateError,
    OAuthStateStore,
    SocialContinuation,
    SocialContinuationStore,
    SocialProvider,
    build_authorization_request,
    exchange_code,
    redirect_uri,
)
from app.domains.auth.otp import PendingAuth
from app.domains.auth.repositories import AuthMembershipRepository, RefreshTokenRepository
from app.domains.auth.schemas import (
    LoginRequest,
    RegisterRequest,
    SocialAuthStartRequest,
    create_organization_slug,
)
from app.domains.tenancy.enums import MembershipRole, TenantStatus, UserStatus
from app.domains.tenancy.models import Tenant, TenantMembership, User
from app.domains.tenancy.repositories import (
    MembershipRepository,
    ProviderIdentityRepository,
    TenantRepository,
    UserRepository,
)


class AuthenticationError(RuntimeError):
    """Base class for expected authentication workflow failures."""


class RegistrationConflictError(AuthenticationError):
    """Raised when a registration identity or requested slug already exists."""


class InvalidCredentialsError(AuthenticationError):
    """Raised for a failed login without revealing which check failed."""


class InvalidRefreshTokenError(AuthenticationError):
    """Raised when an opaque refresh credential is missing, expired, or invalid."""


class RefreshTokenReuseError(AuthenticationError):
    """Raised after a replayed refresh token causes its family to be revoked."""


class AccountUnavailableError(AuthenticationError):
    """Raised when a valid identity no longer has an active tenant session."""


@dataclass(frozen=True, slots=True)
class AuthTokens:
    access_token: str
    refresh_token: str
    expires_in: int


@dataclass(frozen=True, slots=True)
class SocialAuthResult:
    status: str
    continuation_token: str | None = None
    profile: OAuthProfile | None = None
    organizations: list[tuple[TenantMembership, Tenant]] | None = None
    pending: PendingAuth | None = None


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _verify_against_dummy(password: str) -> bool:
    return verify_password(password, dummy_password_hash())


class AuthService:
    """Create and rotate tenant-bound login sessions."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.tenants = TenantRepository(session)

    async def prepare_registration(self, request: RegisterRequest) -> PendingAuth:
        email = str(request.email)
        password_hash = await to_thread.run_sync(
            hash_password,
            request.password.get_secret_value(),
        )
        slug = request.organization_slug or create_organization_slug(request.organization_name)
        if request.organization_slug is None and await self.tenants.get_by_slug(slug) is not None:
            slug = f"{slug[:50].rstrip('-')}-{uuid4().hex[:8]}"

        return PendingAuth(
            kind="password_register",
            email=email,
            payload={
                "email": email,
                "password_hash": password_hash,
                "display_name": request.display_name,
                "organization_name": request.organization_name,
                "organization_slug": slug,
            },
        )

    async def prepare_login(self, request: LoginRequest) -> PendingAuth:
        user = await self.users.get_by_email(str(request.email))
        password = request.password.get_secret_value()
        if user is None:
            await to_thread.run_sync(_verify_against_dummy, password)
            raise InvalidCredentialsError("Invalid email, password, or organization")

        verified = user.password_hash is not None and await to_thread.run_sync(
            verify_password, password, user.password_hash
        )
        if not verified or user.status is not UserStatus.ACTIVE:
            raise InvalidCredentialsError("Invalid email, password, or organization")

        selection = await AuthMembershipRepository(self.session).select_for_login(
            user_id=user.id,
            tenant_slug=request.organization_slug,
        )
        if selection is None:
            raise InvalidCredentialsError("Invalid email, password, or organization")
        _membership, tenant = selection
        if tenant.status is not TenantStatus.ACTIVE:
            raise AccountUnavailableError("Organization is not active")

        replacement_hash = None
        if user.password_hash is not None and password_needs_rehash(user.password_hash):
            replacement_hash = await to_thread.run_sync(hash_password, password)

        return PendingAuth(
            kind="password_login",
            email=user.email,
            payload={
                "user_id": str(user.id),
                "tenant_id": str(tenant.id),
                "replacement_password_hash": replacement_hash,
            },
        )

    async def complete_pending_auth(self, pending: PendingAuth) -> AuthTokens:
        if pending.kind == "password_register":
            return await self._complete_password_registration(pending.payload)
        if pending.kind == "password_login":
            return await self._complete_login(pending.payload)
        if pending.kind == "social_register":
            return await self._complete_social_registration(pending.payload)
        if pending.kind == "social_login":
            return await self._complete_login(pending.payload)
        raise InvalidCredentialsError("The verification request is invalid")

    async def _complete_password_registration(
        self,
        payload: dict[str, Any],
    ) -> AuthTokens:
        email = self._required_string(payload, "email")
        password_hash = self._required_string(payload, "password_hash")
        organization_name = self._required_string(payload, "organization_name")
        organization_slug = self._required_string(payload, "organization_slug")
        display_name = payload.get("display_name")
        if display_name is not None and not isinstance(display_name, str):
            raise InvalidCredentialsError("The verification request is invalid")

        try:
            user = await self.users.create(
                email=email,
                password_hash=password_hash,
                display_name=display_name,
                email_verified_at=datetime.now(UTC),
            )
            tenant = await self.tenants.create(
                name=organization_name,
                slug=organization_slug,
            )
            await MembershipRepository(self.session, tenant.id).create(
                user_id=user.id,
                role=MembershipRole.OWNER,
            )
            result = await self._create_session(user_id=user.id, tenant_id=tenant.id)
            await self.session.commit()
            return result
        except IntegrityError as exc:
            await self.session.rollback()
            raise RegistrationConflictError("Email or organization slug is already in use") from exc

    async def _complete_login(self, payload: dict[str, Any]) -> AuthTokens:
        try:
            user_id = UUID(self._required_string(payload, "user_id"))
            tenant_id = UUID(self._required_string(payload, "tenant_id"))
        except ValueError as exc:
            raise InvalidCredentialsError("The verification request is invalid") from exc
        user = await self.users.get_by_id(user_id)
        tenant = await self.tenants.get_by_id(tenant_id)
        if (
            user is None
            or user.status is not UserStatus.ACTIVE
            or tenant is None
            or tenant.status is not TenantStatus.ACTIVE
        ):
            raise AccountUnavailableError("Account or organization is not active")
        async with tenant_session_scope(self.session, tenant_id):
            membership = await MembershipRepository(self.session).get_for_user(user_id)
            if membership is None:
                raise AccountUnavailableError("No active organization is available")
            replacement_hash = payload.get("replacement_password_hash")
            if replacement_hash is not None:
                if not isinstance(replacement_hash, str):
                    raise InvalidCredentialsError("The verification request is invalid")
                user.password_hash = replacement_hash
            if user.email_verified_at is None:
                user.email_verified_at = datetime.now(UTC)
            result = await self._create_session(user_id=user_id, tenant_id=tenant_id)
            await self.session.commit()
            return result

    async def delete_account(
        self,
        *,
        user: User,
        tenant: Tenant,
        membership: TenantMembership,
        password: str,
        confirmation: str,
    ) -> None:
        if confirmation != "DELETE MY ACCOUNT":
            raise InvalidCredentialsError("Type DELETE MY ACCOUNT to confirm account deletion")
        if user.password_hash is None or not await to_thread.run_sync(
            verify_password, password, user.password_hash
        ):
            raise InvalidCredentialsError("Recent authentication is required before deletion")
        memberships = await AuthMembershipRepository(self.session).list_for_login(user_id=user.id)
        if membership.role is MembershipRole.OWNER and len(memberships) == 1:
            await self.session.delete(tenant)
        else:
            await self.session.delete(membership)
            if user.memberships:
                user.memberships = [item for item in user.memberships if item.id != membership.id]
        await self.session.delete(user)
        await self.session.commit()

    async def refresh(self, raw_token: str) -> AuthTokens:
        try:
            tenant_id = get_refresh_token_tenant_id(raw_token)
        except ValueError as exc:
            raise InvalidRefreshTokenError("Invalid refresh token") from exc

        async with tenant_session_scope(self.session, tenant_id):
            refresh_tokens = RefreshTokenRepository(self.session)
            current = await refresh_tokens.get_for_rotation(hash_refresh_token(raw_token))
            if current is None:
                raise InvalidRefreshTokenError("Invalid refresh token")

            if current.revoked_at is not None:
                await refresh_tokens.revoke_family(current.family_id)
                await self.session.commit()
                raise RefreshTokenReuseError("Refresh token reuse detected")

            if _ensure_utc(current.expires_at) <= datetime.now(UTC):
                raise InvalidRefreshTokenError("Refresh token has expired")

            user = await self.users.get_by_id(current.user_id)
            tenant = await self.tenants.get_by_id(current.tenant_id)
            membership = await MembershipRepository(self.session).get_for_user(current.user_id)
            if not self._session_is_active(user=user, tenant=tenant, membership=membership):
                await refresh_tokens.revoke_family(current.family_id)
                await self.session.commit()
                raise AccountUnavailableError("Account or organization is not active")

            replacement_raw = generate_refresh_token(current.tenant_id)
            await refresh_tokens.rotate(
                current,
                new_token_hash=hash_refresh_token(replacement_raw),
                # Keep a fixed family lifetime rather than extending sessions
                # indefinitely with every rotation.
                expires_at=current.expires_at,
            )
            access_token, expires_in = create_access_token(current.user_id, current.tenant_id)
            await self.session.commit()
            return AuthTokens(
                access_token=access_token,
                refresh_token=replacement_raw,
                expires_in=expires_in,
            )

    async def begin_social(
        self,
        provider: str,
        request: SocialAuthStartRequest,
        state_store: OAuthStateStore,
        *,
        user_id: str | None = None,
        tenant_id: str | None = None,
    ) -> str:
        """Create a one-time PKCE state and return the provider URL."""

        if provider not in {"google", "microsoft", "github"}:
            raise OAuthProviderDisabledError("This sign-in provider is not available")
        social_provider = cast(SocialProvider, provider)
        authorization_url, state, oauth_state = build_authorization_request(
            social_provider,
            mode=request.mode,
            redirect=redirect_uri(social_provider),
            user_id=user_id,
            tenant_id=tenant_id,
            organization_slug=request.organization_slug,
        )
        await state_store.put(state, oauth_state, settings.OAUTH_STATE_TTL_SECONDS)
        return authorization_url

    async def complete_social(
        self,
        provider: str,
        *,
        code: str,
        state: str,
        state_store: OAuthStateStore,
        continuation_store: SocialContinuationStore,
    ) -> SocialAuthResult:
        """Validate a provider callback and either sign in or issue one next step."""

        oauth_state = await state_store.consume(state)
        if oauth_state is None:
            raise InvalidCredentialsError("The social sign-in request expired or was already used")
        if provider not in {"google", "microsoft", "github"}:
            raise OAuthProviderDisabledError("This sign-in provider is not available")
        profile = await exchange_code(
            cast(SocialProvider, provider),
            code=code,
            oauth_state=oauth_state,
        )
        identity_repo = ProviderIdentityRepository(self.session)
        identity = await identity_repo.get_by_subject(
            provider=profile.provider,
            issuer=profile.issuer,
            subject=profile.subject,
        )
        if identity is None:
            existing_user = await self.users.get_by_email(profile.email)
            if existing_user is not None:
                token = await self._store_social_continuation(
                    continuation_store,
                    SocialContinuation(kind="link", profile=profile, user_id=str(existing_user.id)),
                )
                return SocialAuthResult(
                    status="account_link_required",
                    continuation_token=token,
                    profile=profile,
                )
            token = await self._store_social_continuation(
                continuation_store,
                SocialContinuation(kind="register", profile=profile),
            )
            return SocialAuthResult(
                status="organization_required",
                continuation_token=token,
                profile=profile,
            )

        user = await self.users.get_by_id(identity.user_id)
        if user is None or user.status is not UserStatus.ACTIVE:
            raise AccountUnavailableError("Account is not active")
        memberships = await AuthMembershipRepository(self.session).list_for_login(user_id=user.id)
        if not memberships:
            raise AccountUnavailableError("No active organization is available")
        selected = None
        if oauth_state.organization_slug is not None:
            selected = next(
                (item for item in memberships if item[1].slug == oauth_state.organization_slug),
                None,
            )
            if selected is None:
                raise InvalidCredentialsError("Invalid organization selection")
        elif len(memberships) == 1:
            selected = memberships[0]
        if selected is None:
            token = await self._store_social_continuation(
                continuation_store,
                SocialContinuation(kind="select", profile=profile, user_id=str(user.id)),
            )
            return SocialAuthResult(
                status="organization_selection_required",
                continuation_token=token,
                profile=profile,
                organizations=memberships,
            )
        _membership, tenant = selected
        if tenant.status is not TenantStatus.ACTIVE:
            raise AccountUnavailableError("Organization is not active")
        return SocialAuthResult(
            status="otp_required",
            profile=profile,
            pending=PendingAuth(
                kind="social_login",
                email=profile.email,
                payload={"user_id": str(user.id), "tenant_id": str(tenant.id)},
            ),
        )

    async def prepare_social_registration(
        self,
        *,
        continuation_token: str,
        organization_name: str | None,
        organization_slug: str | None,
        continuation_store: SocialContinuationStore,
    ) -> PendingAuth:
        continuation = await continuation_store.consume_continuation(continuation_token)
        if continuation is None or continuation.kind != "register":
            raise InvalidCredentialsError(
                "The social registration request expired or was already used"
            )
        profile = continuation.profile
        if not profile.email_verified:
            raise InvalidCredentialsError("The provider email is not verified")
        name = organization_name or (
            f"{profile.display_name or profile.email.split('@', 1)[0]}'s workspace"
        )
        slug = organization_slug or create_organization_slug(name)
        if organization_slug is None and await self.tenants.get_by_slug(slug) is not None:
            slug = f"{slug[:50].rstrip('-')}-{uuid4().hex[:8]}"

        return PendingAuth(
            kind="social_register",
            email=profile.email,
            payload={
                "continuation": continuation.as_dict(),
                "organization_name": name,
                "organization_slug": slug,
            },
        )

    async def _complete_social_registration(
        self,
        payload: dict[str, Any],
    ) -> AuthTokens:
        continuation_value = payload.get("continuation")
        if not isinstance(continuation_value, dict):
            raise InvalidCredentialsError("The verification request is invalid")
        try:
            continuation = SocialContinuation.from_dict(continuation_value)
        except OAuthStateError as exc:
            raise InvalidCredentialsError("The verification request is invalid") from exc
        if continuation.kind != "register":
            raise InvalidCredentialsError("The verification request is invalid")
        profile = continuation.profile
        name = self._required_string(payload, "organization_name")
        slug = self._required_string(payload, "organization_slug")
        try:
            user = await self.users.create(
                email=profile.email,
                password_hash=None,
                display_name=profile.display_name,
                email_verified_at=datetime.now(UTC),
            )
            tenant = await self.tenants.create(name=name, slug=slug)
            await MembershipRepository(self.session, tenant.id).create(
                user_id=user.id,
                role=MembershipRole.OWNER,
            )
            await ProviderIdentityRepository(self.session).create(
                provider=profile.provider,
                issuer=profile.issuer,
                subject=profile.subject,
                user_id=user.id,
                email=profile.email,
                email_verified=profile.email_verified,
            )
            tokens = await self._create_session(user_id=user.id, tenant_id=tenant.id)
            await self.session.commit()
            return tokens
        except IntegrityError as exc:
            await self.session.rollback()
            raise RegistrationConflictError("Email or organization slug is already in use") from exc

    async def prepare_social_selection(
        self,
        *,
        continuation_token: str,
        organization_slug: str,
        continuation_store: SocialContinuationStore,
    ) -> PendingAuth:
        continuation = await continuation_store.consume_continuation(continuation_token)
        if continuation is None or continuation.kind != "select" or continuation.user_id is None:
            raise InvalidCredentialsError(
                "The organization selection request expired or was already used"
            )
        try:
            user_id = UUID(continuation.user_id)
        except ValueError as exc:
            raise InvalidCredentialsError("Invalid organization selection") from exc
        selection = await AuthMembershipRepository(self.session).select_for_login(
            user_id=user_id,
            tenant_slug=organization_slug,
        )
        if selection is None:
            raise InvalidCredentialsError("Invalid organization selection")
        _membership, tenant = selection
        if tenant.status is not TenantStatus.ACTIVE:
            raise AccountUnavailableError("Organization is not active")
        user = await self.users.get_by_id(user_id)
        if user is None or user.status is not UserStatus.ACTIVE:
            raise AccountUnavailableError("Account is not active")
        return PendingAuth(
            kind="social_login",
            email=user.email,
            payload={"user_id": str(user_id), "tenant_id": str(tenant.id)},
        )

    async def link_social_identity(
        self,
        *,
        continuation_token: str,
        current_user_id: UUID,
        continuation_store: SocialContinuationStore,
    ) -> None:
        continuation = await continuation_store.consume_continuation(continuation_token)
        if continuation is None or continuation.kind != "link" or continuation.user_id is None:
            raise InvalidCredentialsError("The account-link request expired or was already used")
        if continuation.user_id != str(current_user_id):
            raise InvalidCredentialsError("The social identity belongs to a different account")
        profile = continuation.profile
        identity_repo = ProviderIdentityRepository(self.session)
        if (
            await identity_repo.get_by_subject(
                provider=profile.provider,
                issuer=profile.issuer,
                subject=profile.subject,
            )
            is not None
        ):
            raise RegistrationConflictError("This social identity is already linked")
        await identity_repo.create(
            provider=profile.provider,
            issuer=profile.issuer,
            subject=profile.subject,
            user_id=current_user_id,
            email=profile.email,
            email_verified=profile.email_verified,
        )
        await self.session.commit()

    @staticmethod
    async def _store_social_continuation(
        store: SocialContinuationStore,
        value: SocialContinuation,
    ) -> str:
        token = uuid4().hex + uuid4().hex
        await store.put_continuation(token, value, settings.OAUTH_STATE_TTL_SECONDS)
        return token

    async def _create_session(self, *, user_id: UUID, tenant_id: UUID) -> AuthTokens:
        refresh_token = generate_refresh_token(tenant_id)
        await RefreshTokenRepository(self.session, tenant_id).create(
            user_id=user_id,
            family_id=uuid4(),
            token_hash=hash_refresh_token(refresh_token),
            expires_at=datetime.now(UTC) + timedelta(days=settings.AUTH_REFRESH_TOKEN_TTL_DAYS),
        )
        access_token, expires_in = create_access_token(user_id, tenant_id)
        return AuthTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
        )

    @staticmethod
    def _required_string(payload: dict[str, Any], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            raise InvalidCredentialsError("The verification request is invalid")
        return value

    @staticmethod
    def _session_is_active(
        *,
        user: User | None,
        tenant: Tenant | None,
        membership: TenantMembership | None,
    ) -> bool:
        return (
            user is not None
            and user.status is UserStatus.ACTIVE
            and tenant is not None
            and tenant.status is TenantStatus.ACTIVE
            and membership is not None
        )


__all__ = [
    "AccountUnavailableError",
    "AuthService",
    "AuthTokens",
    "AuthenticationError",
    "InvalidCredentialsError",
    "InvalidRefreshTokenError",
    "RefreshTokenReuseError",
    "RegistrationConflictError",
]
