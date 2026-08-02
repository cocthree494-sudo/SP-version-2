"""Create global identities and tenant memberships with RLS.

Revision ID: 0002_tenancy
Revises: 0001_enable_pgvector
Create Date: 2026-08-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0002_tenancy"
down_revision: str | None = "0001_enable_pgvector"
branch_labels: tuple[str, ...] | None = None
depends_on: str | None = None


def _enum(*values: str, name: str) -> sa.Enum:
    """Build a portable VARCHAR enum with a database check constraint."""

    return sa.Enum(
        *values,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=16,
    )


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "status",
            _enum("active", "disabled", name="user_status"),
            server_default="active",
            nullable=False,
        ),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.CheckConstraint("length(email) BETWEEN 3 AND 320", name="ck_users_email_length"),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=63), nullable=False),
        sa.Column(
            "status",
            _enum("active", "suspended", name="tenant_status"),
            server_default="active",
            nullable=False,
        ),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.CheckConstraint("length(slug) BETWEEN 2 AND 63", name="ck_tenants_slug_length"),
        sa.PrimaryKeyConstraint("id", name="pk_tenants"),
        sa.UniqueConstraint("slug", name="uq_tenants_slug"),
    )

    op.create_table(
        "tenant_memberships",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "role",
            _enum("owner", "admin", "member", name="membership_role"),
            server_default="member",
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_tenant_memberships_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_tenant_memberships_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tenant_memberships"),
        sa.UniqueConstraint(
            "tenant_id",
            "user_id",
            name="uq_tenant_memberships_tenant_user",
        ),
    )
    op.create_index(
        "ix_tenant_memberships_tenant_id",
        "tenant_memberships",
        ["tenant_id"],
    )
    op.create_index(
        "ix_tenant_memberships_user_id",
        "tenant_memberships",
        ["user_id"],
    )

    # Every tenant-owned table uses the same transaction-local GUC. The
    # application repository also includes tenant_id predicates as defense in
    # depth, and FORCE makes the policy apply to the table owner as well.
    op.execute(sa.text("ALTER TABLE tenant_memberships ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE tenant_memberships FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            """
            CREATE POLICY tenant_memberships_tenant_isolation
            ON tenant_memberships
            USING (
                tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            )
            WITH CHECK (
                tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            )
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("DROP POLICY IF EXISTS tenant_memberships_tenant_isolation ON tenant_memberships")
    )
    op.execute(sa.text("ALTER TABLE tenant_memberships NO FORCE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE tenant_memberships DISABLE ROW LEVEL SECURITY"))
    op.drop_table("tenant_memberships")
    op.drop_table("tenants")
    op.drop_table("users")
