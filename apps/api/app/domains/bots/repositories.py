"""Fail-closed tenant repositories for bots and widget credentials."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import (
    TenantContextError,
    get_current_tenant_id,
    maybe_current_tenant_id,
    set_database_tenant,
)
from app.db.base import utc_now
from app.domains.bots.enums import BotStatus
from app.domains.bots.models import Bot, BotKey


class _TenantRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID | None = None) -> None:
        self.session = session
        self._tenant_id = tenant_id

    def _resolve_tenant_id(self) -> UUID:
        context_tenant_id = maybe_current_tenant_id()
        if self._tenant_id is not None:
            if context_tenant_id is not None and context_tenant_id != self._tenant_id:
                raise TenantContextError("Repository tenant does not match active tenant context")
            return self._tenant_id
        return get_current_tenant_id()

    async def _prepare_scope(self) -> UUID:
        tenant_id = self._resolve_tenant_id()
        await set_database_tenant(self.session, tenant_id)
        return tenant_id


class BotRepository(_TenantRepository):
    """Tenant-scoped bot persistence."""

    async def create(
        self,
        *,
        name: str,
        system_policy: str | None,
        default_language: str,
        status: BotStatus,
        widget_welcome_text: str,
        widget_accent_color: str,
        widget_position: str,
    ) -> Bot:
        tenant_id = await self._prepare_scope()
        bot = Bot(
            tenant_id=tenant_id,
            name=name,
            system_policy=system_policy,
            default_language=default_language,
            status=status,
            widget_welcome_text=widget_welcome_text,
            widget_accent_color=widget_accent_color,
            widget_position=widget_position,
        )
        self.session.add(bot)
        await self.session.flush()
        return bot

    async def list(self) -> list[Bot]:
        tenant_id = await self._prepare_scope()
        result = await self.session.scalars(
            select(Bot)
            .where(Bot.tenant_id == tenant_id)
            .order_by(Bot.created_at, Bot.id)
        )
        return list(result)

    async def get(self, bot_id: UUID) -> Bot | None:
        tenant_id = await self._prepare_scope()
        return await self.session.scalar(
            select(Bot).where(Bot.id == bot_id, Bot.tenant_id == tenant_id)
        )

    async def delete(self, bot: Bot) -> None:
        tenant_id = await self._prepare_scope()
        if bot.tenant_id != tenant_id:
            raise TenantContextError("Cannot delete a bot outside the active tenant")
        await self.session.delete(bot)
        await self.session.flush()


class BotKeyRepository(_TenantRepository):
    """Tenant-scoped publishable-key persistence and revocation."""

    async def create(
        self,
        *,
        bot_id: UUID,
        publishable_key: str,
        label: str,
        allowed_origins: list[str],
    ) -> BotKey:
        tenant_id = await self._prepare_scope()
        key = BotKey(
            tenant_id=tenant_id,
            bot_id=bot_id,
            publishable_key=publishable_key,
            label=label,
            allowed_origins=allowed_origins,
        )
        self.session.add(key)
        await self.session.flush()
        return key

    async def list_for_bot(self, bot_id: UUID) -> list[BotKey]:
        tenant_id = await self._prepare_scope()
        result = await self.session.scalars(
            select(BotKey)
            .where(BotKey.tenant_id == tenant_id, BotKey.bot_id == bot_id)
            .order_by(BotKey.created_at, BotKey.id)
        )
        return list(result)

    async def get(self, *, bot_id: UUID, key_id: UUID) -> BotKey | None:
        tenant_id = await self._prepare_scope()
        return await self.session.scalar(
            select(BotKey).where(
                BotKey.id == key_id,
                BotKey.bot_id == bot_id,
                BotKey.tenant_id == tenant_id,
            )
        )

    async def resolve_active(self, publishable_key: str) -> tuple[BotKey, Bot] | None:
        tenant_id = await self._prepare_scope()
        row = (
            await self.session.execute(
                select(BotKey, Bot)
                .join(
                    Bot,
                    (Bot.id == BotKey.bot_id) & (Bot.tenant_id == BotKey.tenant_id),
                )
                .where(
                    BotKey.publishable_key == publishable_key,
                    BotKey.tenant_id == tenant_id,
                    BotKey.revoked_at.is_(None),
                    Bot.tenant_id == tenant_id,
                    Bot.status == BotStatus.ACTIVE,
                )
                .limit(1)
            )
        ).one_or_none()
        if row is None:
            return None
        return row[0], row[1]

    async def revoke(self, key: BotKey) -> None:
        tenant_id = await self._prepare_scope()
        if key.tenant_id != tenant_id:
            raise TenantContextError("Cannot revoke a key outside the active tenant")
        if key.revoked_at is None:
            key.revoked_at = utc_now()
            await self.session.flush()


__all__ = ["BotKeyRepository", "BotRepository"]
