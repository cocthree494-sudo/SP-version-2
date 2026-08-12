"""Minimal first-party authentication HTTP API."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AccessTokenError, decode_access_token
from app.core.tenancy import tenant_session_scope
from app.db.session import get_db_session
from app.domains.auth.oauth import (
    InMemoryOAuthStateStore,
    OAuthError,
    OAuthExchangeError,
    OAuthProviderDisabledError,
    OAuthStateError,
    RedisOAuthStateStore,
)
from app.domains.auth.schemas import (
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
    response_model=TokenPairResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(payload: RegisterRequest, session: DbSession) -> TokenPairResponse:
    try:
        tokens = await AuthService(session).register(payload)
    except RegistrationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    return _token_response(tokens)


@router.post("/auth/login", response_model=TokenPairResponse)
async def login(payload: LoginRequest, session: DbSession) -> TokenPairResponse:
    try:
        tokens = await AuthService(session).login(payload)
    except InvalidCredentialsError as exc:
        raise _unauthorized(str(exc)) from None
    except AccountUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from None
    return _token_response(tokens)


def _oauth_store(request: Request) -> RedisOAuthStateStore | InMemoryOAuthStateStore:
    store = getattr(request.app.state, "oauth_state_store", None)
    if isinstance(store, (RedisOAuthStateStore, InMemoryOAuthStateStore)):
        return store
    return _fallback_oauth_store


def _social_response(result: SocialAuthResult) -> SocialAuthResponse:
    tokens = result.tokens
    profile = result.profile
    return SocialAuthResponse(
        status=result.status,  # type: ignore[arg-type]
        access_token=tokens.access_token if tokens else None,
        refresh_token=tokens.refresh_token if tokens else None,
        expires_in=tokens.expires_in if tokens else None,
        continuation_token=result.continuation_token,
        email=profile.email if profile else None,
        display_name=profile.display_name if profile else None,
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
    try:
        result = await AuthService(session).complete_social(
            provider,
            code=payload.code,
            state=payload.state,
            state_store=_oauth_store(request),
            continuation_store=_oauth_store(request),
        )
    except (OAuthError, AuthenticationError, ValueError) as exc:
        raise _oauth_http_error(exc) from None
    return _social_response(result)


@router.post("/auth/oauth/register", response_model=TokenPairResponse)
async def social_register(
    payload: SocialAuthCompleteRequest,
    request: Request,
    session: DbSession,
) -> TokenPairResponse:
    try:
        tokens = await AuthService(session).complete_social_registration(
            continuation_token=payload.continuation_token.get_secret_value(),
            organization_name=payload.organization_name,
            organization_slug=payload.organization_slug,
            continuation_store=_oauth_store(request),
        )
    except AuthenticationError as exc:
        raise _oauth_http_error(exc) from None
    return _token_response(tokens)


@router.post("/auth/oauth/select", response_model=TokenPairResponse)
async def social_select(
    payload: SocialAuthCompleteRequest,
    request: Request,
    session: DbSession,
) -> TokenPairResponse:
    if not payload.organization_slug:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Organization slug is required",
        )
    try:
        tokens = await AuthService(session).complete_social_selection(
            continuation_token=payload.continuation_token.get_secret_value(),
            organization_slug=payload.organization_slug,
            continuation_store=_oauth_store(request),
        )
    except AuthenticationError as exc:
        raise _oauth_http_error(exc) from None
    return _token_response(tokens)


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


__all__ = ["AuthContext", "require_auth_context", "router"]
