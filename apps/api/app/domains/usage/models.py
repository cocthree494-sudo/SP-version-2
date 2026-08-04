"""Append-only tenant usage event model."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String, event, func
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from app.db.base import Base, TenantScopedMixin, UUIDPrimaryKeyMixin, utc_now
from app.domains.usage.enums import UsageOperation


def _enum_type(enum_class: type[Any], name: str, length: int) -> SqlEnum:
    return SqlEnum(
        enum_class,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=length,
        values_callable=lambda values: [item.value for item in values],
    )


class UsageEvent(UUIDPrimaryKeyMixin, TenantScopedMixin, Base):
    """One immutable normalized provider operation."""

    __tablename__ = "usage_events"
    __table_args__ = (
        Index("ix_usage_events_tenant_created", "tenant_id", "created_at"),
        Index("ix_usage_events_tenant_bot_created", "tenant_id", "bot_id", "created_at"),
        CheckConstraint("length(provider) BETWEEN 1 AND 100", name="ck_usage_provider_length"),
        CheckConstraint("length(model) BETWEEN 1 AND 200", name="ck_usage_model_length"),
        CheckConstraint("input_tokens >= 0", name="ck_usage_input_tokens_nonnegative"),
        CheckConstraint("output_tokens >= 0", name="ck_usage_output_tokens_nonnegative"),
        CheckConstraint(
            "cache_read_tokens >= 0",
            name="ck_usage_cache_read_tokens_nonnegative",
        ),
        CheckConstraint(
            "cache_write_tokens >= 0",
            name="ck_usage_cache_write_tokens_nonnegative",
        ),
        CheckConstraint("latency_ms >= 0", name="ck_usage_latency_ms_nonnegative"),
        CheckConstraint(
            "estimated_cost_microusd >= 0",
            name="ck_usage_estimated_cost_nonnegative",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    bot_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    conversation_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    operation: Mapped[UsageOperation] = mapped_column(
        _enum_type(UsageOperation, "usage_operation", 16),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    input_tokens: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default="0",
    )
    output_tokens: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default="0",
    )
    cache_read_tokens: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default="0",
    )
    cache_write_tokens: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default="0",
    )
    latency_ms: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default="0",
    )
    estimated_cost_microusd: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default="0",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )


class UsageEventMutationError(RuntimeError):
    """Raised when ORM code attempts to change immutable usage history."""


@event.listens_for(UsageEvent, "before_update")
@event.listens_for(UsageEvent, "before_delete")
def _prevent_usage_event_mutation(
    _mapper: Mapper[UsageEvent],
    _connection: Any,
    _target: UsageEvent,
) -> None:
    raise UsageEventMutationError("usage_events is append-only")


__all__ = ["UsageEvent", "UsageEventMutationError"]
