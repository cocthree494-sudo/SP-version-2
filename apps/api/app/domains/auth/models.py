"""Persistence model for revocable, rotated refresh-token sessions."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TenantScopedModel


class RefreshToken(TenantScopedModel):
    """A hashed opaque credential in one tenant-bound login session."""

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        CheckConstraint(
            "length(token_hash) = 64",
            name="ck_refresh_tokens_token_hash_length",
        ),
        Index("ix_refresh_tokens_family_id", "family_id"),
        Index("ix_refresh_tokens_expires_at", "expires_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Override the shared tenant key with its organization foreign key.
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    family_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
        nullable=True,
    )


__all__ = ["RefreshToken"]
