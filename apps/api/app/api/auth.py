"""Minimal first-party authentication HTTP API."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass, replace
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import AccessTokenError, decode_access_token
from app.core.tenancy import tenant_session_scope
from app.db.session import get_db_session
from app.domains.auth.email import AuthEmailDeliveryError, InMemoryAuthEmailSender
from app.domains.auth.oauth import (
    InMemoryOAuthStateStore,
    OAuthError,
    OAuthExchangeError,
    OAuthProviderDisabledError,
    OAuthStateError,
    RedisOAuthStateStore,
)
from app.domains.auth.otp import (
    AuthOtpChallenge,
    AuthOtpError,
    AuthOtpExpiredError,
    AuthOtpInvalidError,
    AuthOtpLockedError,
    AuthOtpRateLimitError,
    AuthOtpService,
    AuthOtpUnavailableError,
    InMemoryAuthOtpStore,
)
from app.domains.auth.schemas import (
    AccountDeletionRequest,
    AuthChallengeResponse,
    AuthOtpChallengeRequest,
    AuthOtpVerifyRequest,
    CurrentTenantResponse,
    LoginRequest,
    MeResponse,
    RefreshRequest,
    RegisterRequest,
    SocialAuthCallbackRequest,
    SocialAuthCompleteRequest,
    SocialAuthLinkRequest,
    SocialAuthResponse,
    SocialAuthStartRequest,
    SocialAuthStartResponse,
    TokenPairResponse,
)
from app.domains.auth.service import (
    AccountUnavailableError,
    AuthenticationError,
    AuthService,
    AuthTokens,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    RefreshTokenReuseError,
    RegistrationConflictError,
    SocialAuthResult,
)
from app.domains.tenancy.enums import TenantStatus, UserStatus
from app.domains.tenancy.models import Tenant, TenantMembership, User
from app.domains.tenancy.repositories import (
    MembershipRepository,
    TenantRepository,
    UserRepository,
)

router = APIRouter(prefix="/v1", tags=["authentication"])
bearer_scheme = HTTPBearer(auto_error=False)
DbSession = Annotated[AsyncSession, Depends(get_db_session)]
_fallback_oauth_store = InMemoryOAuthStateStore()
_fallback_otp_store = InMemoryAuthOtpStore()
_fallback_email_sender = InMemoryAuthEmailSender()


@dataclass(frozen=True, slots=True)
class AuthContext:
    user: User
    tenant: Tenant
    membership: TenantMembership


def _unauthorized(detail: str = "Invalid or expired access token") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _token_response(tokens: AuthTokens) -> TokenPairResponse:
    return TokenPairResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


def _challenge_response(challenge: AuthOtpChallenge) -> AuthChallengeResponse:
    return AuthChallengeResponse(
        challenge_id=challenge.challenge_id,
        email_hint=challenge.email_hint,
        flow=challenge.flow,
        expires_in=challenge.expires_in,
        resend_after=challenge.resend_after,
    )


def _otp_service(request: Request) -> AuthOtpService:
    store = getattr(request.app.state, "auth_otp_store", _fallback_otp_store)
    sender = getattr(request.app.state, "auth_email_sender", _fallback_email_sender)
    return AuthOtpService(store, sender)


def _client_ip(request: Request) -> str:
    for header in ("x-relay-client-ip", "cf-connecting-ip", "x-forwarded-for"):
        value = request.headers.get(header)
        if value:
            return value.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def _admin_flow(request: Request) -> bool:
    return request.headers.get("x-relay-admin-flow") == "1"


def _mark_admin_flow(request: Request, pending: PendingAuth) -> PendingAuth:
    if not _admin_flow(request):
        return pending
    payload = {**pending.payload, "admin_flow": True}
    return replace(pending, email=settings.platform_admin_otp_email, payload=payload)


def _otp_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AuthOtpRateLimitError):
        return HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after)},
        )
    if isinstance(exc, AuthOtpExpiredError):
        return HTTPException(status_code=status.HTTP_410_GONE, detail=str(exc))
    if isinstance(exc, AuthOtpLockedError):
        return HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc))
    if isinstance(exc, AuthOtpInvalidError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, AuthEmailDeliveryError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="We could not send the verification email. Please try again.",
        )
    if isinstance(exc, AuthOtpUnavailableError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The verification service is temporarily unavailable.",
        )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="The verification service is temporarily unavailable.",
    )


async def require_auth_context(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    session: DbSession,
) -> AsyncGenerator[AuthContext, None]:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise _unauthorized()
    try:
        claims = decode_access_token(credentials.credentials)
    except AccessTokenError:
        raise _unauthorized() from None

    user = await UserRepository(session).get_by_id(claims.user_id)
    tenant = await TenantRepository(session).get_by_id(claims.tenant_id)
    if (
        user is None
        or user.status is not UserStatus.ACTIVE
        or tenant is None
        or tenant.status is not TenantStatus.ACTIVE
    ):
        raise _unauthorized()

    async with tenant_session_scope(session, claims.tenant_id):
        membership = await MembershipRepository(session).get_for_user(claims.user_id)
        if membership is None:
            raise _unauthorized()
        yield AuthContext(user=user, tenant=tenant, membership=membership)


CurrentAuth = Annotated[AuthContext, Depends(require_auth_context)]


@router.post(
    "/auth/register",
    response_model=AuthChallengeResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def register(
    payload: RegisterRequest,
    request: Request,
    session: DbSession,
) -> AuthChallengeResponse:
    if _admin_flow(request):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Admin access supports Google sign-in only",
        )
    try:
        pending = _mark_admin_flow(
            request,
            await AuthService(session).prepare_registration(payload),
        )
        challenge = await _otp_service(request).start(
            pending,
            client_ip=_client_ip(request),
        )
    except RegistrationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    except (AuthOtpError, AuthEmailDeliveryError) as exc:
        raise _otp_http_error(exc) from None
    return _challenge_response(challenge)


@router.post("/auth/login", response_model=AuthChallengeResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    session: DbSession,
) -> AuthChallengeResponse:
    if _admin_flow(request):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Admin access supports Google sign-in only",
        )
    try:
        pending = _mark_admin_flow(
            request,
            await AuthService(session).prepare_login(payload),
        )
        challenge = await _otp_service(request).start(
            pending,
            client_ip=_client_ip(request),
        )
    except InvalidCredentialsError as exc:
        raise _unauthorized(str(exc)) from None
    except AccountUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from None
    except (AuthOtpError, AuthEmailDeliveryError) as exc:
        raise _otp_http_error(exc) from None
    return _challenge_response(challenge)


@router.post("/auth/otp/status", response_model=AuthChallengeResponse)
async def otp_status(
    payload: AuthOtpChallengeRequest,
    request: Request,
) -> AuthChallengeResponse:
    try:
        challenge = await _otp_service(request).status(
            payload.challenge_id.get_secret_value()
        )
    except AuthOtpError as exc:
        raise _otp_http_error(exc) from None
    return _challenge_response(challenge)


@router.post("/auth/otp/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def otp_cancel(
    payload: AuthOtpChallengeRequest,
    request: Request,
) -> None:
    try:
        await _otp_service(request).cancel(payload.challenge_id.get_secret_value())
    except AuthOtpError as exc:
        raise _otp_http_error(exc) from None


@router.post("/auth/otp/resend", response_model=AuthChallengeResponse)
async def otp_resend(
    payload: AuthOtpChallengeRequest,
    request: Request,
) -> AuthChallengeResponse:
    try:
        challenge = await _otp_service(request).resend(
            payload.challenge_id.get_secret_value(),
            client_ip=_client_ip(request),
        )
    except (AuthOtpError, AuthEmailDeliveryError) as exc:
        raise _otp_http_error(exc) from None
    return _challenge_response(challenge)


@router.post("/auth/otp/verify", response_model=TokenPairResponse)
async def otp_verify(
    payload: AuthOtpVerifyRequest,
    request: Request,
    session: DbSession,
) -> TokenPairResponse:
    try:
        pending = await _otp_service(request).verify(
            payload.challenge_id.get_secret_value(),
            payload.code.get_secret_value(),
        )
        tokens = await AuthService(session).complete_pending_auth(pending)
    except (AuthOtpError, AuthEmailDeliveryError) as exc:
        raise _otp_http_error(exc) from None
    except AuthenticationError as exc:
        raise _oauth_http_error(exc) from None
    return _token_response(tokens)


def _oauth_store(request: Request) -> RedisOAuthStateStore | InMemoryOAuthStateStore:
    store = getattr(request.app.state, "oauth_state_store", None)
    if isinstance(store, (RedisOAuthStateStore, InMemoryOAuthStateStore)):
        return store
    return _fallback_oauth_store


def _social_response(
    result: SocialAuthResult,
    challenge: AuthOtpChallenge | None = None,
) -> SocialAuthResponse:
    profile = result.profile
    return SocialAuthResponse(
        status=result.status,  # type: ignore[arg-type]
        continuation_token=result.continuation_token,
        email=profile.email if profile else None,
        display_name=profile.display_name if profile else None,
        challenge_id=challenge.challenge_id if challenge else None,
        email_hint=challenge.email_hint if challenge else None,
        flow=challenge.flow if challenge else None,
        resend_after=challenge.resend_after if challenge else None,
        expires_in=challenge.expires_in if challenge else None,
        organizations=[
            CurrentTenantResponse(
                id=tenant.id,
                name=tenant.name,
                slug=tenant.slug,
                status=tenant.status,
            )
            for _membership, tenant in (result.organizations or [])
        ],
    )


def _oauth_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, OAuthProviderDisabledError):
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    if isinstance(exc, OAuthStateError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, OAuthExchangeError):
        return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    if isinstance(exc, AccountUnavailableError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, InvalidCredentialsError):
        return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    if isinstance(exc, RegistrationConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Social sign-in failed")


@router.post(
    "/auth/oauth/{provider}/start",
    response_model=SocialAuthStartResponse,
)
async def social_start(
    provider: str,
    payload: SocialAuthStartRequest,
    request: Request,
    session: DbSession,
) -> SocialAuthStartResponse:
    if _admin_flow(request) and provider != "google":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Admin access supports Google sign-in only",
        )
    try:
        authorization_url = await AuthService(session).begin_social(
            provider,
            payload,
            _oauth_store(request),
        )
    except (OAuthError, ValueError) as exc:
        raise _oauth_http_error(exc) from None
    return SocialAuthStartResponse(provider=provider, authorization_url=authorization_url)  # type: ignore[arg-type]


@router.post(
    "/auth/oauth/{provider}/callback",
    response_model=SocialAuthResponse,
)
async def social_callback(
    provider: str,
    payload: SocialAuthCallbackRequest,
    request: Request,
    session: DbSession,
) -> SocialAuthResponse:
    if _admin_flow(request) and provider != "google":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Admin access supports Google sign-in only",
        )
    try:
        result = await AuthService(session).complete_social(
            provider,
            code=payload.code,
            state=payload.state,
            state_store=_oauth_store(request),
            continuation_store=_oauth_store(request),
        )
        challenge = None
        if result.pending is not None:
            result = replace(result, pending=_mark_admin_flow(request, result.pending))
            challenge = await _otp_service(request).start(
                result.pending,
                client_ip=_client_ip(request),
            )
    except (OAuthError, AuthenticationError, ValueError) as exc:
        raise _oauth_http_error(exc) from None
    except (AuthOtpError, AuthEmailDeliveryError) as exc:
        raise _otp_http_error(exc) from None
    return _social_response(result, challenge)


@router.post("/auth/oauth/register", response_model=AuthChallengeResponse)
async def social_register(
    payload: SocialAuthCompleteRequest,
    request: Request,
    session: DbSession,
) -> AuthChallengeResponse:
    try:
        pending = _mark_admin_flow(
            request,
            await AuthService(session).prepare_social_registration(
                continuation_token=payload.continuation_token.get_secret_value(),
                organization_name=payload.organization_name,
                organization_slug=payload.organization_slug,
                continuation_store=_oauth_store(request),
            ),
        )
        challenge = await _otp_service(request).start(
            pending,
            client_ip=_client_ip(request),
        )
    except AuthenticationError as exc:
        raise _oauth_http_error(exc) from None
    except (AuthOtpError, AuthEmailDeliveryError) as exc:
        raise _otp_http_error(exc) from None
    return _challenge_response(challenge)


@router.post("/auth/oauth/select", response_model=AuthChallengeResponse)
async def social_select(
    payload: SocialAuthCompleteRequest,
    request: Request,
    session: DbSession,
) -> AuthChallengeResponse:
    if not payload.organization_slug:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Organization slug is required",
        )
    try:
        pending = _mark_admin_flow(
            request,
            await AuthService(session).prepare_social_selection(
                continuation_token=payload.continuation_token.get_secret_value(),
                organization_slug=payload.organization_slug,
                continuation_store=_oauth_store(request),
            ),
        )
        challenge = await _otp_service(request).start(
            pending,
            client_ip=_client_ip(request),
        )
    except AuthenticationError as exc:
        raise _oauth_http_error(exc) from None
    except (AuthOtpError, AuthEmailDeliveryError) as exc:
        raise _otp_http_error(exc) from None
    return _challenge_response(challenge)


@router.post("/auth/oauth/link", status_code=status.HTTP_204_NO_CONTENT)
async def social_link(
    payload: SocialAuthLinkRequest,
    request: Request,
    session: DbSession,
    context: CurrentAuth,
) -> None:
    try:
        await AuthService(session).link_social_identity(
            continuation_token=payload.continuation_token.get_secret_value(),
            current_user_id=context.user.id,
            continuation_store=_oauth_store(request),
        )
    except AuthenticationError as exc:
        raise _oauth_http_error(exc) from None


@router.post("/auth/refresh", response_model=TokenPairResponse)
async def refresh(payload: RefreshRequest, session: DbSession) -> TokenPairResponse:
    try:
        tokens = await AuthService(session).refresh(payload.refresh_token.get_secret_value())
    except RefreshTokenReuseError as exc:
        raise _unauthorized(str(exc)) from None
    except InvalidRefreshTokenError as exc:
        raise _unauthorized(str(exc)) from None
    except AccountUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from None
    return _token_response(tokens)


@router.get("/me", response_model=MeResponse)
async def me(context: CurrentAuth) -> MeResponse:
    return MeResponse(
        id=context.user.id,
        email=context.user.email,
        display_name=context.user.display_name,
        email_verified_at=context.user.email_verified_at,
        status=context.user.status,
        created_at=context.user.created_at,
        tenant=CurrentTenantResponse(
            id=context.tenant.id,
            name=context.tenant.name,
            slug=context.tenant.slug,
            status=context.tenant.status,
        ),
        role=context.membership.role,
    )


@router.post("/account/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    payload: AccountDeletionRequest, context: CurrentAuth, session: DbSession
) -> None:
    try:
        await AuthService(session).delete_account(
            user=context.user,
            tenant=context.tenant,
            membership=context.membership,
            password=payload.password.get_secret_value(),
            confirmation=payload.confirmation,
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from None


__all__ = ["AuthContext", "require_auth_context", "router"]
