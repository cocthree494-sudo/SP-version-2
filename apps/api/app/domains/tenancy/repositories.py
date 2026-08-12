"""Tenant-aware repositories with fail-closed query predicates."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import (
    TenantContextError,
    get_current_tenant_id,
    maybe_current_tenant_id,
    set_database_tenant,
)
from app.domains.tenancy.enums import MembershipRole, TenantStatus, UserStatus
from app.domains.tenancy.models import ProviderIdentity, Tenant, TenantMembership, User


def normalize_email(email: str) -> str:
    """Normalize login identity consistently before persistence and lookup."""

    return email.strip().casefold()


def normalize_slug(slug: str) -> str:
    """Normalize organization slugs consistently before persistence and lookup."""

    return slug.strip().casefold()


class UserRepository:
    """Global user identity persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        email: str,
        password_hash: str | None,
        display_name: str | None = None,
        status: UserStatus = UserStatus.ACTIVE,
    ) -> User:
        user = User(
            email=normalize_email(email),
            password_hash=password_hash,
            display_name=display_name,
            status=status,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def get_by_id(self, user_id: UUID) -> User | None:
        return await self.session.scalar(select(User).where(User.id == user_id))

    async def get_by_email(self, email: str) -> User | None:
        return await self.session.scalar(select(User).where(User.email == normalize_email(email)))


class ProviderIdentityRepository:
    """Global external-identity bindings with stable provider subjects."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_subject(
        self,
        *,
        provider: str,
        issuer: str,
        subject: str,
    ) -> ProviderIdentity | None:
        return await self.session.scalar(
            select(ProviderIdentity).where(
                ProviderIdentity.provider == provider,
                ProviderIdentity.issuer == issuer,
                ProviderIdentity.subject == subject,
            )
        )

    async def create(
        self,
        *,
        provider: str,
        issuer: str,
        subject: str,
        user_id: UUID,
        email: str,
        email_verified: bool,
    ) -> ProviderIdentity:
        identity = ProviderIdentity(
            provider=provider,
            issuer=issuer,
            subject=subject,
            user_id=user_id,
            email=normalize_email(email),
            email_verified=email_verified,
        )
        self.session.add(identity)
        await self.session.flush()
        return identity


class TenantRepository:
    """Organization persistence; member access is checked separately."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        name: str,
        slug: str,
        settings: dict[str, Any] | None = None,
        status: TenantStatus = TenantStatus.ACTIVE,
    ) -> Tenant:
        tenant = Tenant(
            name=name.strip(),
            slug=normalize_slug(slug),
            settings={} if settings is None else settings,
            status=status,
        )
        self.session.add(tenant)
        await self.session.flush()
        return tenant

    async def get_by_id(self, tenant_id: UUID) -> Tenant | None:
        return await self.session.scalar(select(Tenant).where(Tenant.id == tenant_id))

    async def get_by_slug(self, slug: str) -> Tenant | None:
        return await self.session.scalar(select(Tenant).where(Tenant.slug == normalize_slug(slug)))


class MembershipRepository:
    """Tenant-scoped membership persistence.

    Every method resolves one tenant before issuing SQL and includes that key
    in its predicate. A missing context raises instead of falling back to an
    unscoped query, which protects callers even when PostgreSQL RLS is absent
    in local tests.
    """

    def __init__(self, session: AsyncSession, tenant_id: UUID | None = None) -> None:
        self.session = session
        self._tenant_id = tenant_id

    def _resolve_tenant_id(self) -> UUID:
        context_tenant_id = maybe_current_tenant_id()
        if self._tenant_id is not None:
            if context_tenant_id is not None and context_tenant_id != self._tenant_id:
                raise TenantContextError(
                    "Repository tenant does not match the active tenant context"
                )
            return self._tenant_id
        return get_current_tenant_id()

    async def _prepare_scope(self) -> UUID:
        tenant_id = self._resolve_tenant_id()
        await set_database_tenant(self.session, tenant_id)
        return tenant_id

    async def create(
        self,
        *,
        user_id: UUID,
        role: MembershipRole = MembershipRole.MEMBER,
    ) -> TenantMembership:
        tenant_id = await self._prepare_scope()
        membership = TenantMembership(
            tenant_id=tenant_id,
            user_id=user_id,
            role=role,
        )
        self.session.add(membership)
        await self.session.flush()
        return membership

    async def get_by_id(self, membership_id: UUID) -> TenantMembership | None:
        tenant_id = await self._prepare_scope()
        return await self.session.scalar(
            select(TenantMembership).where(
                TenantMembership.id == membership_id,
                TenantMembership.tenant_id == tenant_id,
            )
        )

    async def get_for_user(self, user_id: UUID) -> TenantMembership | None:
        tenant_id = await self._prepare_scope()
        return await self.session.scalar(
            select(TenantMembership).where(
                TenantMembership.user_id == user_id,
                TenantMembership.tenant_id == tenant_id,
            )
        )

    async def list_for_tenant(self) -> list[TenantMembership]:
        tenant_id = await self._prepare_scope()
        result = await self.session.scalars(
            select(TenantMembership)
            .where(TenantMembership.tenant_id == tenant_id)
            .order_by(TenantMembership.created_at)
        )
        return list(result)

    async def delete(self, membership_id: UUID) -> bool:
        membership = await self.get_by_id(membership_id)
        if membership is None:
            return False
        await self.session.delete(membership)
        await self.session.flush()
        return True


__all__ = [
    "MembershipRepository",
    "ProviderIdentityRepository",
    "TenantRepository",
    "UserRepository",
    "normalize_email",
    "normalize_slug",
]
