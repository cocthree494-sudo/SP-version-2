"""Conversation continuity, rolling compaction, and retention hooks."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domains.bots.repositories import BotRepository
from app.domains.chat.enums import ConversationMessageRole, ConversationStatus
from app.domains.chat.models import Conversation, ConversationMessage
from app.domains.chat.repositories import ConversationRepository


class ConversationDomainError(RuntimeError):
    """Base class for expected conversation failures."""


class ConversationNotFoundError(ConversationDomainError):
    pass


class ConversationClosedError(ConversationDomainError):
    pass


class InvalidConversationMessageError(ConversationDomainError):
    pass


class RollingSummaryProvider(Protocol):
    """Provider-neutral interface for server-generated rolling summaries."""

    async def summarize(
        self,
        *,
        existing_summary: str | None,
        messages: Sequence[ConversationMessage],
    ) -> str: ...


class ConversationRetentionHook(Protocol):
    """Extension point for storage/cache cleanup before a retained thread is purged."""

    async def before_purge(self, conversation: Conversation) -> None: ...


class NoopConversationRetentionHook:
    async def before_purge(self, conversation: Conversation) -> None:
        del conversation


@dataclass(frozen=True, slots=True)
class ConversationContext:
    conversation: Conversation
    summary: str | None
    recent_messages: list[ConversationMessage]


def _expiry(now: datetime | None = None) -> datetime:
    current = now or datetime.now(UTC)
    return current + timedelta(days=settings.CONVERSATION_RETENTION_DAYS)


class ConversationService:
    """Transaction-composable tenant-scoped conversation operations."""

    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.repository = ConversationRepository(session, tenant_id)

    async def create(
        self,
        *,
        bot_id: UUID,
        channel: str,
        external_id: str | None = None,
        now: datetime | None = None,
    ) -> Conversation:
        bot = await BotRepository(self.session, self.tenant_id).get(bot_id)
        if bot is None:
            raise ConversationNotFoundError("Bot not found in conversation tenant")
        normalized_channel = channel.strip().casefold()
        if not 1 <= len(normalized_channel) <= 32:
            raise ConversationDomainError("Conversation channel must be 1-32 characters")
        normalized_external = external_id.strip() if external_id is not None else None
        if normalized_external == "":
            normalized_external = None
        if normalized_external is not None and len(normalized_external) > 200:
            raise ConversationDomainError("Conversation external ID is too long")
        return await self.repository.create(
            bot_id=bot_id,
            channel=normalized_channel,
            external_id=normalized_external,
            retention_expires_at=_expiry(now),
        )

    async def append_message(
        self,
        conversation_id: UUID,
        *,
        role: ConversationMessageRole,
        content: str,
        citations: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> ConversationMessage:
        normalized_content = content.strip()
        if not normalized_content:
            raise InvalidConversationMessageError("Conversation messages cannot be empty")
        if len(normalized_content) > settings.CONVERSATION_MESSAGE_MAX_CHARS:
            raise InvalidConversationMessageError("Conversation message is too long")
        conversation = await self.repository.get(conversation_id, for_update=True)
        if conversation is None:
            raise ConversationNotFoundError("Conversation not found")
        if conversation.status is not ConversationStatus.ACTIVE:
            raise ConversationClosedError("Conversation is closed")
        return await self.repository.append_message(
            conversation,
            role=role,
            content=normalized_content,
            citations=citations,
            metadata=metadata,
            retention_expires_at=_expiry(now),
        )

    async def load_context(
        self,
        conversation_id: UUID,
        *,
        recent_limit: int | None = None,
    ) -> ConversationContext:
        conversation = await self.repository.get(conversation_id)
        if conversation is None:
            raise ConversationNotFoundError("Conversation not found")
        limit = recent_limit or settings.CONVERSATION_RECENT_MESSAGE_LIMIT
        if not 1 <= limit <= 100:
            raise ValueError("recent_limit must be between 1 and 100")
        messages = await self.repository.list_recent_messages(
            conversation.id,
            after_sequence=conversation.summary_through_sequence,
            limit=limit,
        )
        return ConversationContext(
            conversation=conversation,
            summary=conversation.summary,
            recent_messages=messages,
        )

    async def compact(
        self,
        conversation_id: UUID,
        summarizer: RollingSummaryProvider,
        *,
        keep_recent: int | None = None,
    ) -> bool:
        conversation = await self.repository.get(conversation_id, for_update=True)
        if conversation is None:
            raise ConversationNotFoundError("Conversation not found")
        retained_count = keep_recent or settings.CONVERSATION_RECENT_MESSAGE_LIMIT
        if not 1 <= retained_count <= 100:
            raise ValueError("keep_recent must be between 1 and 100")
        uncompacted = await self.repository.list_messages_after(
            conversation.id,
            after_sequence=conversation.summary_through_sequence,
        )
        if len(uncompacted) <= retained_count:
            return False
        compactable = uncompacted[:-retained_count]
        summary = (
            await summarizer.summarize(
                existing_summary=conversation.summary,
                messages=compactable,
            )
        ).strip()
        if not summary:
            raise ConversationDomainError("Rolling summary provider returned an empty summary")
        if len(summary) > settings.CONVERSATION_SUMMARY_MAX_CHARS:
            raise ConversationDomainError("Rolling summary exceeds the configured limit")
        conversation.summary = summary
        conversation.summary_through_sequence = compactable[-1].sequence
        await self.session.flush()
        return True

    async def purge_expired(
        self,
        *,
        before: datetime,
        hook: ConversationRetentionHook | None = None,
        limit: int = 100,
    ) -> int:
        if before.tzinfo is None or before.utcoffset() is None:
            raise ValueError("Retention boundary must include a timezone")
        if not 1 <= limit <= 1000:
            raise ValueError("Retention limit must be between 1 and 1000")
        retention_hook = hook or NoopConversationRetentionHook()
        due = await self.repository.list_due_for_retention(
            before=before.astimezone(UTC),
            limit=limit,
        )
        for conversation in due:
            await retention_hook.before_purge(conversation)
            await self.repository.delete(conversation)
        return len(due)


__all__ = [
    "ConversationClosedError",
    "ConversationContext",
    "ConversationDomainError",
    "ConversationNotFoundError",
    "ConversationRetentionHook",
    "ConversationService",
    "InvalidConversationMessageError",
    "NoopConversationRetentionHook",
    "RollingSummaryProvider",
]
