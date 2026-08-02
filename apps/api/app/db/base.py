"""Shared SQLAlchemy declarative base and model mixins.

The application uses UUID primary keys and timezone-aware UTC timestamps for
all persisted domain records. Tenant-owned models should also inherit
``TenantScopedMixin`` so the tenant key is required and indexed consistently.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, MetaData, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utc_now() -> datetime:
    """Return the current timezone-aware UTC time for Python-side defaults."""

    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Declarative base shared by every application model."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPrimaryKeyMixin:
    """Provide an application-generated UUID primary key."""

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )


class TimestampMixin:
    """Provide timezone-aware creation and update timestamps in UTC."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
        nullable=False,
    )


class TenantScopedMixin:
    """Mark a model as tenant-owned and require an indexed tenant key.

    Repositories and request handlers must still apply the active tenant
    predicate explicitly. This mixin makes omitting the key from a tenant
    table structurally difficult and gives future row-level-security policies
    a consistent column name.
    """

    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )


class UUIDTimestampModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Convenience base for global records with UUID and timestamp fields."""

    __abstract__ = True


class TenantScopedModel(UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin, Base):
    """Convenience base for tenant-owned records."""

    __abstract__ = True


__all__ = [
    "NAMING_CONVENTION",
    "Base",
    "TenantScopedMixin",
    "TenantScopedModel",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    "UUIDTimestampModel",
    "utc_now",
]
