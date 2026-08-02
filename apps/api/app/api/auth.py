"""Minimal first-party authentication HTTP API."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AccessTokenError, decode_access_token
from app.core.tenancy import tenant_session_scope
from app.db.session import get_db_session
from app.domains.auth.schemas import (
    CurrentTenantResponse,
    LoginRequest,
    MeResponse,
    RefreshRequest,
    RegisterRequest,
    TokenPairResponse,
)
from app.domains.auth.service import (
    AccountUnavailableError,
    AuthService,
    AuthTokens,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    RefreshTokenReuseError,
    RegistrationConflictError,
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
