"""Add rotated refresh sessions and user-scoped membership resolution.

Revision ID: 0003_auth
Revises: 0002_tenancy
Create Date: 2026-08-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0003_auth"
down_revision: str | None = "0002_tenancy"
branch_labels: tuple[str, ...] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("family_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.CheckConstraint(
            "length(token_hash) = 64",
            name="ck_refresh_tokens_token_hash_length",
        ),
        sa.ForeignKeyConstraint(
            ["replaced_by_id"],
            ["refresh_tokens.id"],
            name="fk_refresh_tokens_replaced_by_id_refresh_tokens",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_refresh_tokens_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_refresh_tokens_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_refresh_tokens"),
        sa.UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
    )
    op.create_index("ix_refresh_tokens_expires_at", "refresh_tokens", ["expires_at"])
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])
    op.create_index("ix_refresh_tokens_tenant_id", "refresh_tokens", ["tenant_id"])
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])

    op.execute(sa.text("ALTER TABLE refresh_tokens ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE refresh_tokens FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            """
            CREATE POLICY refresh_tokens_tenant_isolation
            ON refresh_tokens
            USING (
                tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            )
            WITH CHECK (
                tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            )
            """
        )
    )

    # Login occurs before a tenant can be selected. After the password is
    # verified, this SELECT-only policy permits resolving exactly that user's
    # memberships via a transaction-local app.user_id. Tenant-scoped reads and
    # all writes remain protected by the original tenant policy.
    op.execute(
        sa.text(
            """
            CREATE POLICY tenant_memberships_authenticated_user_select
            ON tenant_memberships
            FOR SELECT
            USING (
                user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
            )
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP POLICY IF EXISTS refresh_tokens_tenant_isolation ON refresh_tokens"))
    op.execute(sa.text("ALTER TABLE refresh_tokens NO FORCE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE refresh_tokens DISABLE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            "DROP POLICY IF EXISTS tenant_memberships_authenticated_user_select "
            "ON tenant_memberships"
        )
    )
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_tenant_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_family_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_expires_at", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
