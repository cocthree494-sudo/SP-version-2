"""Narrow persistence helpers used only at the authentication boundary."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import (
    TenantContextError,
    get_current_tenant_id,
    maybe_current_tenant_id,
    set_database_tenant,
    set_database_user,
)
from app.db.base import utc_now
from app.domains.auth.models import RefreshToken
from app.domains.tenancy.models import Tenant, TenantMembership
from app.domains.tenancy.repositories import normalize_slug


class AuthMembershipRepository:
    """Resolve one verified user's own organizations before tenant selection.

    This is deliberately separate from ``MembershipRepository``. Its only
    query includes a verified ``user_id`` predicate, and PostgreSQL RLS checks
    the matching transaction-local ``app.user_id`` value.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def select_for_login(
        self,
        *,
        user_id: UUID,
        tenant_slug: str | None = None,
    ) -> tuple[TenantMembership, Tenant] | None:
        await set_database_user(self.session, user_id)
        statement = (
            select(TenantMembership, Tenant)
            .join(Tenant, Tenant.id == TenantMembership.tenant_id)
            .where(TenantMembership.user_id == user_id)
            .order_by(TenantMembership.created_at, TenantMembership.id)
            .limit(1)
        )
        if tenant_slug is not None:
            statement = statement.where(Tenant.slug == normalize_slug(tenant_slug))

        row = (await self.session.execute(statement)).one_or_none()
        if row is None:
            return None
        return row[0], row[1]


class RefreshTokenRepository:
    """Store only hashes and perform refresh rotation under a row lock."""

    def __init__(self, session: AsyncSession, tenant_id: UUID | None = None) -> None:
        self.session = session
        self._tenant_id = tenant_id

    def _resolve_tenant_id(self) -> UUID:
        context_tenant_id = maybe_current_tenant_id()
        if self._tenant_id is not None:
            if context_tenant_id is not None and context_tenant_id != self._tenant_id:
                raise TenantContextError(
                    "Refresh-token tenant does not match the active tenant context"
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
        family_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> RefreshToken:
        tenant_id = await self._prepare_scope()
        refresh_token = RefreshToken(
            user_id=user_id,
            tenant_id=tenant_id,
            family_id=family_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.session.add(refresh_token)
        await self.session.flush()
        return refresh_token

    async def get_for_rotation(self, token_hash: str) -> RefreshToken | None:
        tenant_id = await self._prepare_scope()
        return await self.session.scalar(
            select(RefreshToken)
            .where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.tenant_id == tenant_id,
            )
            .with_for_update()
        )

    async def rotate(
        self,
        current: RefreshToken,
        *,
        new_token_hash: str,
        expires_at: datetime,
    ) -> RefreshToken:
        now = utc_now()
        replacement = await self.create(
            user_id=current.user_id,
            family_id=current.family_id,
            token_hash=new_token_hash,
            expires_at=expires_at,
        )
        current.revoked_at = now
        current.replaced_by_id = replacement.id
        await self.session.flush()
        return replacement

    async def revoke_family(self, family_id: UUID) -> None:
        tenant_id = await self._prepare_scope()
        now = utc_now()
        await self.session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.family_id == family_id,
                RefreshToken.tenant_id == tenant_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now, updated_at=now)
        )


__all__ = ["AuthMembershipRepository", "RefreshTokenRepository"]
