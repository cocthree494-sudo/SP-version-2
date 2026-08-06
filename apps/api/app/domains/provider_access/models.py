"""Tenant-scoped encrypted generation credentials and routing policy."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TenantScopedModel
from app.domains.provider_access.enums import (
    GenerationProvider,
    ProviderCredentialStatus,
    ProviderRoutingMode,
)


def _enum_type(enum_class: type[Any], name: str, length: int) -> SqlEnum:
    return SqlEnum(
        enum_class,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=length,
        values_callable=lambda values: [item.value for item in values],
    )


class ProviderCredential(TenantScopedModel):
    """Recoverable provider secret stored only as an encrypted envelope."""

    __tablename__ = "provider_credentials"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_provider_credentials_tenant_id_id"),
        UniqueConstraint(
            "tenant_id",
            "fingerprint",
            name="uq_provider_credentials_tenant_fingerprint",
        ),
        CheckConstraint("length(label) BETWEEN 1 AND 100", name="ck_provider_credentials_label"),
        CheckConstraint(
            "length(low_cost_model_id) BETWEEN 1 AND 200",
            name="ck_provider_credentials_low_model",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[GenerationProvider] = mapped_column(
        _enum_type(GenerationProvider, "generation_provider", 32),
        nullable=False,
    )
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    encrypted_secret: Mapped[str] = mapped_column(Text, nullable=False)
    wrapped_data_key: Mapped[str] = mapped_column(Text, nullable=False)
    key_version: Mapped[str] = mapped_column(String(64), nullable=False)
    masked_secret: Mapped[str] = mapped_column(String(32), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    low_cost_model_id: Mapped[str] = mapped_column(String(200), nullable=False)
    strong_model_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[ProviderCredentialStatus] = mapped_column(
        _enum_type(ProviderCredentialStatus, "provider_credential_status", 16),
        default=ProviderCredentialStatus.UNVERIFIED,
        server_default=ProviderCredentialStatus.UNVERIFIED.value,
        nullable=False,
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProviderPolicy(TenantScopedModel):
    """One explicit generation routing policy per tenant."""

    __tablename__ = "provider_policies"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_provider_policies_tenant_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mode: Mapped[ProviderRoutingMode] = mapped_column(
        _enum_type(ProviderRoutingMode, "provider_routing_mode", 48),
        default=ProviderRoutingMode.PLATFORM_ONLY,
        server_default=ProviderRoutingMode.PLATFORM_ONLY.value,
        nullable=False,
    )
    credential_order: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        server_default="[]",
        nullable=False,
    )


__all__ = ["ProviderCredential", "ProviderPolicy"]
