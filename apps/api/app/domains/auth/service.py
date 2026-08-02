"""Transactional authentication workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
from app.domains.auth.repositories import AuthMembershipRepository, RefreshTokenRepository
from app.domains.auth.schemas import LoginRequest, RegisterRequest, create_organization_slug
from app.domains.tenancy.enums import MembershipRole, TenantStatus, UserStatus
from app.domains.tenancy.models import Tenant, TenantMembership, User
from app.domains.tenancy.repositories import (
    MembershipRepository,
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

    async def register(self, request: RegisterRequest) -> AuthTokens:
        email = str(request.email)
        password_hash = await to_thread.run_sync(
            hash_password,
            request.password.get_secret_value(),
        )
        if await self.users.get_by_email(email) is not None:
            raise RegistrationConflictError("Email is already registered")

        slug = request.organization_slug or create_organization_slug(request.organization_name)
        existing_tenant = await self.tenants.get_by_slug(slug)
        if existing_tenant is not None:
            if request.organization_slug is not None:
                raise RegistrationConflictError("Organization slug is already in use")
            slug = f"{slug[:50].rstrip('-')}-{uuid4().hex[:8]}"

        try:
            user = await self.users.create(
                email=email,
                password_hash=password_hash,
                display_name=request.display_name,
            )
            tenant = await self.tenants.create(name=request.organization_name, slug=slug)
            await MembershipRepository(self.session, tenant.id).create(
                user_id=user.id,
                role=MembershipRole.OWNER,
            )
            result = await self._create_session(user_id=user.id, tenant_id=tenant.id)
            await self.session.commit()
            return result
        except IntegrityError as exc:
            await self.session.rollback()
            raise RegistrationConflictError(
                "Email or organization slug is already in use"
            ) from exc

    async def login(self, request: LoginRequest) -> AuthTokens:
        user = await self.users.get_by_email(str(request.email))
        password = request.password.get_secret_value()
        if user is None:
            await to_thread.run_sync(_verify_against_dummy, password)
            raise InvalidCredentialsError("Invalid email, password, or organization")

        verified = await to_thread.run_sync(verify_password, password, user.password_hash)
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

        if password_needs_rehash(user.password_hash):
            user.password_hash = await to_thread.run_sync(hash_password, password)

        result = await self._create_session(user_id=user.id, tenant_id=tenant.id)
        await self.session.commit()
        return result

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

    async def _create_session(self, *, user_id: UUID, tenant_id: UUID) -> AuthTokens:
        refresh_token = generate_refresh_token(tenant_id)
        await RefreshTokenRepository(self.session, tenant_id).create(
            user_id=user_id,
            family_id=uuid4(),
            token_hash=hash_refresh_token(refresh_token),
            expires_at=datetime.now(UTC)
            + timedelta(days=settings.AUTH_REFRESH_TOKEN_TTL_DAYS),
        )
        access_token, expires_in = create_access_token(user_id, tenant_id)
        return AuthTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
        )

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
