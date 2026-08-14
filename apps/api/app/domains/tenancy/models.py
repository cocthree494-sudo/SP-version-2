"""SQLAlchemy models for global identities and tenant membership."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TenantScopedModel, UUIDTimestampModel
from app.domains.tenancy.enums import MembershipRole, TenantStatus, UserStatus


def _enum_type(enum_class: type[Any], name: str, length: int) -> SqlEnum:
    """Store enum values as portable strings with database-side checks."""

    return SqlEnum(
        enum_class,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=length,
        values_callable=lambda values: [item.value for item in values],
    )


class User(UUIDTimestampModel):
    """Global login identity; membership determines tenant access."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        CheckConstraint(
            "length(email) BETWEEN 3 AND 320",
            name="ck_users_email_length",
        ),
    )

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    # Social-only identities intentionally have no password hash. Password
    # login rejects those users until they explicitly set a password.
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[UserStatus] = mapped_column(
        _enum_type(UserStatus, "user_status", 16),
        default=UserStatus.ACTIVE,
        server_default=UserStatus.ACTIVE.value,
        nullable=False,
    )
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    memberships: Mapped[list[TenantMembership]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class ProviderIdentity(UUIDTimestampModel):
    """Stable external identity binding for an OAuth/OIDC provider."""

    __tablename__ = "provider_identities"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "issuer",
            "subject",
            name="uq_provider_identities_provider_issuer_subject",
        ),
        UniqueConstraint(
            "user_id",
            "provider",
            name="uq_provider_identities_user_provider",
        ),
    )

    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    issuer: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    email_verified: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        server_default="false",
    )


class Tenant(UUIDTimestampModel):
    """Organization boundary for all tenant-owned product data."""

    __tablename__ = "tenants"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_tenants_slug"),
        CheckConstraint(
            "length(slug) BETWEEN 2 AND 63",
            name="ck_tenants_slug_length",
        ),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(63), nullable=False)
    status: Mapped[TenantStatus] = mapped_column(
        _enum_type(TenantStatus, "tenant_status", 16),
        default=TenantStatus.ACTIVE,
        server_default=TenantStatus.ACTIVE.value,
        nullable=False,
    )
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )

    memberships: Mapped[list[TenantMembership]] = relationship(
        back_populates="tenant",
        cascade="all, delete-orphan",
    )


class TenantMembership(TenantScopedModel):
    """A user's role in exactly one tenant."""

    __tablename__ = "tenant_memberships"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "user_id",
            name="uq_tenant_memberships_tenant_user",
        ),
    )

    # Override the shared tenant key with a foreign key to the organization.
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[MembershipRole] = mapped_column(
        _enum_type(MembershipRole, "membership_role", 16),
        default=MembershipRole.MEMBER,
        server_default=MembershipRole.MEMBER.value,
        nullable=False,
    )

    tenant: Mapped[Tenant] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")


__all__ = ["ProviderIdentity", "Tenant", "TenantMembership", "User"]
