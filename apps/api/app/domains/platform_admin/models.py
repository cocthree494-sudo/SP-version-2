"""Global platform-admin authorization and immutable audit records."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import UUIDTimestampModel


class PlatformAdminStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


class PlatformAdmin(UUIDTimestampModel):
    """Global authorization, intentionally separate from tenant membership."""

    __tablename__ = "platform_admins"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    status: Mapped[PlatformAdminStatus] = mapped_column(
        SqlEnum(
            PlatformAdminStatus,
            name="platform_admin_status",
            native_enum=False,
            create_constraint=True,
            length=16,
            values_callable=lambda values: [item.value for item in values],
        ),
        default=PlatformAdminStatus.ACTIVE,
        server_default=PlatformAdminStatus.ACTIVE.value,
        nullable=False,
    )
    granted_by_user_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PlatformAdminAuditLog(UUIDTimestampModel):
    """Append-only, redacted record of every platform-admin read or mutation."""

    __tablename__ = "platform_admin_audit_logs"
    __table_args__ = (
        CheckConstraint("length(action) BETWEEN 1 AND 120", name="ck_admin_audit_action"),
        CheckConstraint("length(outcome) BETWEEN 1 AND 32", name="ck_admin_audit_outcome"),
        UniqueConstraint(
            "actor_user_id",
            "action",
            "target_type",
            "target_id",
            "idempotency_key",
            name="uq_admin_audit_idempotency",
        ),
    )

    actor_user_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    change_summary: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, server_default="{}", nullable=False
    )


__all__ = ["PlatformAdmin", "PlatformAdminAuditLog", "PlatformAdminStatus"]
