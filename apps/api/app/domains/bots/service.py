"""Bot lifecycle, key rotation, and public credential resolution."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import tenant_session_scope
from app.domains.bots.enums import BotStatus
from app.domains.bots.models import Bot, BotKey
from app.domains.bots.repositories import BotKeyRepository, BotRepository
from app.domains.bots.schemas import (
    BotCreateRequest,
    BotKeyCreateRequest,
    BotKeyUpdateRequest,
    BotUpdateRequest,
    normalize_origin,
)


class BotDomainError(RuntimeError):
    """Base class for expected bot-domain failures."""


class BotNotFoundError(BotDomainError):
    """Raised when a bot is absent from the active tenant."""


class BotKeyNotFoundError(BotDomainError):
    """Raised when a key is absent from the active tenant and bot."""


class RevokedBotKeyError(BotDomainError):
    """Raised when attempting to mutate an already revoked credential."""


@dataclass(frozen=True, slots=True)
class ResolvedWidgetCredential:
    """Minimal trusted identity produced by public-key and origin checks."""

    tenant_id: UUID
    bot_id: UUID
    key_id: UUID


def generate_publishable_key(tenant_id: UUID) -> str:
    """Create a public tenant-addressable identifier with 256-bit entropy."""

    return f"pk_{tenant_id}.{secrets.token_urlsafe(32)}"


def get_publishable_key_tenant_id(publishable_key: str) -> UUID:
    """Parse the non-secret tenant address from a publishable key."""

    prefix, separator, random_part = publishable_key.partition(".")
    if separator != "." or not prefix.startswith("pk_") or not random_part:
        raise ValueError("Invalid publishable key format")
    return UUID(prefix.removeprefix("pk_"))


class BotService:
    """Tenant-scoped dashboard operations for bots and public keys."""

    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.bots = BotRepository(session, tenant_id)
        self.keys = BotKeyRepository(session, tenant_id)

    async def create_bot(self, payload: BotCreateRequest) -> Bot:
        bot = await self.bots.create(
            name=payload.name,
            system_policy=payload.system_policy,
            default_language=payload.default_language,
            status=payload.status,
            widget_welcome_text=payload.widget_welcome_text,
            widget_accent_color=payload.widget_accent_color,
            widget_position=payload.widget_position,
        )
        await self.session.commit()
        return bot

    async def list_bots(self) -> list[Bot]:
        return await self.bots.list()

    async def get_bot(self, bot_id: UUID) -> Bot:
        bot = await self.bots.get(bot_id)
        if bot is None:
            raise BotNotFoundError("Bot not found")
        return bot

    async def update_bot(self, bot_id: UUID, payload: BotUpdateRequest) -> Bot:
        bot = await self.get_bot(bot_id)
        fields = payload.model_fields_set
        if "name" in fields:
            bot.name = cast(str, payload.name)
        if "system_policy" in fields:
            bot.system_policy = payload.system_policy
        if "default_language" in fields:
            bot.default_language = cast(str, payload.default_language)
        if "status" in fields:
            bot.status = cast(BotStatus, payload.status)
        if "widget_welcome_text" in fields:
            bot.widget_welcome_text = cast(str, payload.widget_welcome_text)
        if "widget_accent_color" in fields:
            bot.widget_accent_color = cast(str, payload.widget_accent_color)
        if "widget_position" in fields:
            bot.widget_position = cast(str, payload.widget_position)
        await self.session.commit()
        return bot

    async def delete_bot(self, bot_id: UUID) -> None:
        bot = await self.get_bot(bot_id)
        await self.bots.delete(bot)
        await self.session.commit()

    async def create_key(self, bot_id: UUID, payload: BotKeyCreateRequest) -> BotKey:
        await self.get_bot(bot_id)
        key = await self.keys.create(
            bot_id=bot_id,
            publishable_key=generate_publishable_key(self.tenant_id),
            label=payload.label,
            allowed_origins=payload.allowed_origins,
        )
        await self.session.commit()
        return key

    async def list_keys(self, bot_id: UUID) -> list[BotKey]:
        await self.get_bot(bot_id)
        return await self.keys.list_for_bot(bot_id)

    async def update_key(
        self,
        bot_id: UUID,
        key_id: UUID,
        payload: BotKeyUpdateRequest,
    ) -> BotKey:
        await self.get_bot(bot_id)
        key = await self.keys.get(bot_id=bot_id, key_id=key_id)
        if key is None:
            raise BotKeyNotFoundError("Widget key not found")
        if key.revoked_at is not None:
            raise RevokedBotKeyError("A revoked widget key cannot be changed")
        if "label" in payload.model_fields_set:
            key.label = cast(str, payload.label)
        if "allowed_origins" in payload.model_fields_set:
            key.allowed_origins = cast(list[str], payload.allowed_origins)
        await self.session.commit()
        return key

    async def revoke_key(self, bot_id: UUID, key_id: UUID) -> None:
        await self.get_bot(bot_id)
        key = await self.keys.get(bot_id=bot_id, key_id=key_id)
        if key is None:
            raise BotKeyNotFoundError("Widget key not found")
        await self.keys.revoke(key)
        await self.session.commit()


async def resolve_widget_credential(
    session: AsyncSession,
    *,
    publishable_key: str,
    origin: str,
) -> ResolvedWidgetCredential | None:
    """Validate key format, tenant scope, revocation, bot status, and origin."""

    try:
        tenant_id = get_publishable_key_tenant_id(publishable_key)
        normalized_origin = normalize_origin(origin)
    except ValueError:
        return None

    async with tenant_session_scope(session, tenant_id):
        resolved = await BotKeyRepository(session).resolve_active(publishable_key)
        if resolved is None:
            return None
        key, bot = resolved
        if normalized_origin not in key.allowed_origins:
            return None
        return ResolvedWidgetCredential(
            tenant_id=tenant_id,
            bot_id=bot.id,
            key_id=key.id,
        )


__all__ = [
    "BotDomainError",
    "BotKeyNotFoundError",
    "BotNotFoundError",
    "BotService",
    "ResolvedWidgetCredential",
    "RevokedBotKeyError",
    "generate_publishable_key",
    "get_publishable_key_tenant_id",
    "resolve_widget_credential",
]
