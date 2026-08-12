"""Tenant-scoped external channel installation metadata."""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TenantScopedModel


class ChannelType(StrEnum):
    TELEGRAM_PERSONAL = "telegram_personal"
    WHATSAPP_BUSINESS = "whatsapp_business"
    FACEBOOK_PAGE = "facebook_page"
    EMAIL = "email"


class ChannelStatus(StrEnum):
    PENDING = "pending"
    CONNECTED = "connected"
    PAUSED = "paused"
    REVOKED = "revoked"
    ERROR = "error"


def _enum_type(enum_class: type[StrEnum], name: str, length: int) -> SqlEnum:
    return SqlEnum(
        enum_class,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=length,
        values_callable=lambda values: [item.value for item in values],
    )


class ChannelInstallation(TenantScopedModel):
    __tablename__ = "channel_installations"
    __table_args__ = (
        CheckConstraint("length(external_identity) BETWEEN 1 AND 255", name="ck_channel_identity"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel_type: Mapped[ChannelType] = mapped_column(
        _enum_type(ChannelType, "channel_type", 32), nullable=False
    )
    external_identity: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[ChannelStatus] = mapped_column(
        _enum_type(ChannelStatus, "channel_status", 16),
        default=ChannelStatus.PENDING,
        server_default=ChannelStatus.PENDING.value,
        nullable=False,
    )
    conversation_scope: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    credential_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    consent_record: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    expires_at: Mapped[Any | None] = mapped_column(DateTime(timezone=True), nullable=True)


__all__ = ["ChannelInstallation", "ChannelStatus", "ChannelType"]
