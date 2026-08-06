"""SQLAlchemy models for bots and their public widget credentials."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TenantScopedModel
from app.domains.bots.enums import BotStatus


def _enum_type(enum_class: type[Any], name: str, length: int) -> SqlEnum:
    return SqlEnum(
        enum_class,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=length,
        values_callable=lambda values: [item.value for item in values],
    )


class Bot(TenantScopedModel):
    """Tenant-owned policy and language configuration for one support bot."""

    __tablename__ = "bots"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_bots_tenant_id_id"),
        CheckConstraint("length(name) BETWEEN 1 AND 200", name="ck_bots_name_length"),
        CheckConstraint(
            "length(default_language) BETWEEN 2 AND 35",
            name="ck_bots_default_language_length",
        ),
        CheckConstraint(
            "length(widget_welcome_text) BETWEEN 1 AND 160",
            name="ck_bots_widget_welcome_length",
        ),
        CheckConstraint(
            "length(widget_accent_color) = 7 "
            "AND substr(widget_accent_color, 1, 1) = '#'",
            name="ck_bots_widget_accent_hex",
        ),
        CheckConstraint(
            "widget_position IN ('left', 'right')",
            name="ck_bots_widget_position",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    system_policy: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_language: Mapped[str] = mapped_column(
        String(35),
        default="auto",
        server_default="auto",
        nullable=False,
    )
    widget_welcome_text: Mapped[str] = mapped_column(
        String(160),
        default="How can we help?",
        server_default="How can we help?",
        nullable=False,
    )
    widget_accent_color: Mapped[str] = mapped_column(
        String(7),
        default="#194f46",
        server_default="#194f46",
        nullable=False,
    )
    widget_position: Mapped[str] = mapped_column(
        String(5),
        default="right",
        server_default="right",
        nullable=False,
    )
    status: Mapped[BotStatus] = mapped_column(
        _enum_type(BotStatus, "bot_status", 16),
        default=BotStatus.ACTIVE,
        server_default=BotStatus.ACTIVE.value,
        nullable=False,
    )

    keys: Mapped[list[BotKey]] = relationship(
        back_populates="bot",
        cascade="all, delete-orphan",
    )


class BotKey(TenantScopedModel):
    """Revocable public identifier and exact browser-origin allow-list."""

    __tablename__ = "bot_keys"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "bot_id"],
            ["bots.tenant_id", "bots.id"],
            name="fk_bot_keys_tenant_bot_bots",
            ondelete="CASCADE",
        ),
        UniqueConstraint("publishable_key", name="uq_bot_keys_publishable_key"),
        CheckConstraint(
            "length(publishable_key) BETWEEN 80 AND 128",
            name="ck_bot_keys_publishable_key_length",
        ),
        CheckConstraint("length(label) BETWEEN 1 AND 100", name="ck_bot_keys_label_length"),
    )

    tenant_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    bot_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    publishable_key: Mapped[str] = mapped_column(String(128), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    allowed_origins: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        server_default="[]",
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    bot: Mapped[Bot] = relationship(back_populates="keys")


__all__ = ["Bot", "BotKey"]
