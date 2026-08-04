"""Tests for shared SQLAlchemy model conventions."""

from datetime import UTC
from uuid import UUID

from sqlalchemy import DateTime, inspect

from app.db.base import (
    NAMING_CONVENTION,
    Base,
    TenantScopedModel,
    UUIDTimestampModel,
    utc_now,
)


class GlobalRecord(UUIDTimestampModel):
    __tablename__ = "test_global_records"


class TenantRecord(TenantScopedModel):
    __tablename__ = "test_tenant_records"


# These mapped classes exercise the production mixins but are not application
# schema. Keep them out of Base.metadata so Alembic parity checks are order-safe.
Base.metadata.remove(GlobalRecord.__table__)
Base.metadata.remove(TenantRecord.__table__)


def test_base_has_stable_constraint_naming_convention() -> None:
    assert Base.metadata.naming_convention == NAMING_CONVENTION
    assert NAMING_CONVENTION["pk"] == "pk_%(table_name)s"


def test_global_model_uses_uuid_and_utc_timestamps() -> None:
    columns = inspect(GlobalRecord).columns

    assert columns.id.type.python_type is UUID
    assert isinstance(columns.created_at.type, DateTime)
    assert isinstance(columns.updated_at.type, DateTime)
    assert columns.created_at.type.timezone is True
    assert columns.updated_at.type.timezone is True
    assert columns.id.primary_key is True
    assert columns.created_at.nullable is False
    assert columns.updated_at.nullable is False
    assert columns.created_at.default is not None
    assert columns.updated_at.default is not None
    assert utc_now().tzinfo is UTC


def test_tenant_model_requires_indexed_tenant_id() -> None:
    tenant_column = inspect(TenantRecord).columns.tenant_id

    assert tenant_column.type.python_type is UUID
    assert tenant_column.nullable is False
    assert tenant_column.index is True
