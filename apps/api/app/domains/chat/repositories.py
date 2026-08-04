"""Fail-closed repositories for conversations and ordered messages."""

from __future__ import annotations

from datetime import datetime
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
from app.domains.chat.enums import ConversationMessageRole
from app.domains.chat.models import Conversation, ConversationMessage


class ConversationRepository:
    """Persist exactly one tenant's conversation state."""

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

    async def create(
        self,
        *,
        bot_id: UUID,
        channel: str,
        external_id: str | None,
        retention_expires_at: datetime,
    ) -> Conversation:
        tenant_id = await self._prepare_scope()
        conversation = Conversation(
            tenant_id=tenant_id,
            bot_id=bot_id,
            channel=channel,
            external_id=external_id,
            retention_expires_at=retention_expires_at,
        )
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    async def get(
        self,
        conversation_id: UUID,
        *,
        for_update: bool = False,
    ) -> Conversation | None:
        tenant_id = await self._prepare_scope()
        statement = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant_id,
        )
        if for_update:
            statement = statement.with_for_update()
        result: Conversation | None = await self.session.scalar(statement)
        return result

    async def append_message(
        self,
        conversation: Conversation,
        *,
        role: ConversationMessageRole,
        content: str,
        citations: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
        retention_expires_at: datetime,
    ) -> ConversationMessage:
        tenant_id = await self._prepare_scope()
        if conversation.tenant_id != tenant_id:
            raise TenantContextError("Cannot append to a conversation outside the active tenant")
        sequence = conversation.next_message_sequence
        conversation.next_message_sequence += 1
        conversation.retention_expires_at = retention_expires_at
        message = ConversationMessage(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            sequence=sequence,
            role=role,
            content=content,
            citations=citations or [],
            message_metadata=metadata or {},
        )
        self.session.add(message)
        await self.session.flush()
        return message

    async def list_messages_after(
        self,
        conversation_id: UUID,
        *,
        after_sequence: int,
    ) -> list[ConversationMessage]:
        tenant_id = await self._prepare_scope()
        result = await self.session.scalars(
            select(ConversationMessage)
            .where(
                ConversationMessage.tenant_id == tenant_id,
                ConversationMessage.conversation_id == conversation_id,
                ConversationMessage.sequence > after_sequence,
            )
            .order_by(ConversationMessage.sequence)
        )
        return list(result)

    async def list_recent_messages(
        self,
        conversation_id: UUID,
        *,
        after_sequence: int,
        limit: int,
    ) -> list[ConversationMessage]:
        tenant_id = await self._prepare_scope()
        result = await self.session.scalars(
            select(ConversationMessage)
            .where(
                ConversationMessage.tenant_id == tenant_id,
                ConversationMessage.conversation_id == conversation_id,
                ConversationMessage.sequence > after_sequence,
            )
            .order_by(ConversationMessage.sequence.desc())
            .limit(limit)
        )
        return list(reversed(list(result)))

    async def list_due_for_retention(
        self,
        *,
        before: datetime,
        limit: int,
    ) -> list[Conversation]:
        tenant_id = await self._prepare_scope()
        result = await self.session.scalars(
            select(Conversation)
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.retention_expires_at <= before,
            )
            .order_by(Conversation.retention_expires_at, Conversation.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(result)

    async def delete(self, conversation: Conversation) -> None:
        tenant_id = await self._prepare_scope()
        if conversation.tenant_id != tenant_id:
            raise TenantContextError("Cannot delete a conversation outside the active tenant")
        await self.session.delete(conversation)
        await self.session.flush()


__all__ = ["ConversationRepository"]
