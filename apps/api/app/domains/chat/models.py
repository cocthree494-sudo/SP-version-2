"""Tenant-owned conversation and message persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TenantScopedModel
from app.domains.chat.enums import ConversationMessageRole, ConversationStatus


def _enum_type(enum_class: type[Any], name: str, length: int) -> SqlEnum:
    return SqlEnum(
        enum_class,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=length,
        values_callable=lambda values: [item.value for item in values],
    )


class Conversation(TenantScopedModel):
    """Channel-neutral thread with rolling context and retention metadata."""

    __tablename__ = "conversations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "bot_id"],
            ["bots.tenant_id", "bots.id"],
            name="fk_conversations_tenant_bot_bots",
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_conversations_tenant_id_id"),
        UniqueConstraint(
            "tenant_id",
            "bot_id",
            "channel",
            "external_id",
            name="uq_conversations_tenant_bot_channel_external",
        ),
        Index("ix_conversations_tenant_bot_updated", "tenant_id", "bot_id", "updated_at"),
        Index(
            "ix_conversations_tenant_retention",
            "tenant_id",
            "retention_expires_at",
        ),
        CheckConstraint(
            "length(channel) BETWEEN 1 AND 32",
            name="ck_conversations_channel_length",
        ),
        CheckConstraint(
            "external_id IS NULL OR length(external_id) BETWEEN 1 AND 200",
            name="ck_conversations_external_id_length",
        ),
        CheckConstraint(
            "summary_through_sequence >= 0",
            name="ck_conversations_summary_sequence_nonnegative",
        ),
        CheckConstraint(
            "next_message_sequence >= 1",
            name="ck_conversations_next_sequence_positive",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    bot_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[ConversationStatus] = mapped_column(
        _enum_type(ConversationStatus, "conversation_status", 16),
        default=ConversationStatus.ACTIVE,
        server_default=ConversationStatus.ACTIVE.value,
        nullable=False,
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_through_sequence: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    next_message_sequence: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default="1",
        nullable=False,
    )
    retention_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    messages: Mapped[list[ConversationMessage]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ConversationMessage.sequence",
    )


class ConversationMessage(TenantScopedModel):
    """One ordered, tenant-bound turn in a conversation."""

    __tablename__ = "messages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            name="fk_messages_tenant_conversation_conversations",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "tenant_id",
            "conversation_id",
            "sequence",
            name="uq_messages_tenant_conversation_sequence",
        ),
        Index(
            "ix_messages_tenant_conversation_created",
            "tenant_id",
            "conversation_id",
            "created_at",
        ),
        CheckConstraint("sequence >= 1", name="ck_messages_sequence_positive"),
        CheckConstraint("length(content) >= 1", name="ck_messages_content_nonempty"),
    )

    tenant_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    conversation_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[ConversationMessageRole] = mapped_column(
        _enum_type(ConversationMessageRole, "conversation_message_role", 16),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
        server_default="[]",
        nullable=False,
    )
    message_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        default=dict,
        server_default="{}",
        nullable=False,
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


__all__ = ["Conversation", "ConversationMessage"]
