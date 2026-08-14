"""Safe voice-agent configuration and idempotent provider events."""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TenantScopedModel


class VoiceStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    PAUSED = "paused"
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


class VoiceAgentInstallation(TenantScopedModel):
    __tablename__ = "voice_agent_installations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "phone_number", name="uq_voice_tenant_phone"),
        CheckConstraint("length(phone_number) BETWEEN 3 AND 32", name="ck_voice_phone_length"),
        CheckConstraint("retention_days BETWEEN 0 AND 365", name="ck_voice_retention_days"),
        CheckConstraint("monthly_cost_limit_usd BETWEEN 1 AND 100000", name="ck_voice_cost_limit"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    bot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("bots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(
        String(32), nullable=False, default="twilio", server_default="twilio"
    )
    phone_number: Mapped[str] = mapped_column(String(32), nullable=False)
    language: Mapped[str] = mapped_column(
        String(16), nullable=False, default="auto", server_default="auto"
    )
    voice: Mapped[str] = mapped_column(
        String(64), nullable=False, default="alloy", server_default="alloy"
    )
    business_hours: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, server_default="{}", nullable=False
    )
    outbound_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    recording_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    retention_days: Mapped[int] = mapped_column(default=0, server_default="0", nullable=False)
    monthly_cost_limit_usd: Mapped[int] = mapped_column(
        default=100, server_default="100", nullable=False
    )
    provider_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[VoiceStatus] = mapped_column(
        _enum_type(VoiceStatus, "voice_status", 16),
        default=VoiceStatus.PENDING,
        server_default="pending",
        nullable=False,
    )


class VoiceWebhookEvent(TenantScopedModel):
    __tablename__ = "voice_webhook_events"
    __table_args__ = (UniqueConstraint("tenant_id", "event_id", name="uq_voice_webhook_event"),)

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    installation_id: Mapped[UUID] = mapped_column(
        ForeignKey("voice_agent_installations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, server_default="{}", nullable=False
    )
    received_at: Mapped[Any | None] = mapped_column(DateTime(timezone=True), nullable=True)


__all__ = ["VoiceAgentInstallation", "VoiceStatus", "VoiceWebhookEvent"]
