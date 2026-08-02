"""Create tenant-scoped bots and public widget credentials.

Revision ID: 0004_bots
Revises: 0003_auth
Create Date: 2026-08-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0004_bots"
down_revision: str | None = "0003_auth"
branch_labels: tuple[str, ...] | None = None
depends_on: str | None = None


def _bot_status() -> sa.Enum:
    return sa.Enum(
        "active",
        "disabled",
        name="bot_status",
        native_enum=False,
        create_constraint=True,
        length=16,
    )


def _enable_tenant_rls(table_name: str, policy_name: str) -> None:
    op.execute(sa.text(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            f"""
            CREATE POLICY {policy_name}
            ON {table_name}
            USING (
                tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            )
            WITH CHECK (
                tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            )
            """
        )
    )


def upgrade() -> None:
    op.create_table(
        "bots",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("system_policy", sa.Text(), nullable=True),
        sa.Column("default_language", sa.String(length=35), server_default="auto", nullable=False),
        sa.Column(
            "status",
            _bot_status(),
            server_default="active",
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(default_language) BETWEEN 2 AND 35",
            name="ck_bots_default_language_length",
        ),
        sa.CheckConstraint("length(name) BETWEEN 1 AND 200", name="ck_bots_name_length"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_bots_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_bots"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_bots_tenant_id_id"),
    )
    op.create_index("ix_bots_tenant_id", "bots", ["tenant_id"])

    op.create_table(
        "bot_keys",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("bot_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("publishable_key", sa.String(length=128), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("allowed_origins", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(label) BETWEEN 1 AND 100",
            name="ck_bot_keys_label_length",
        ),
        sa.CheckConstraint(
            "length(publishable_key) BETWEEN 80 AND 128",
            name="ck_bot_keys_publishable_key_length",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "bot_id"],
            ["bots.tenant_id", "bots.id"],
            name="fk_bot_keys_tenant_bot_bots",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_bot_keys"),
        sa.UniqueConstraint("publishable_key", name="uq_bot_keys_publishable_key"),
    )
    op.create_index("ix_bot_keys_bot_id", "bot_keys", ["bot_id"])
    op.create_index("ix_bot_keys_tenant_id", "bot_keys", ["tenant_id"])

    _enable_tenant_rls("bots", "bots_tenant_isolation")
    _enable_tenant_rls("bot_keys", "bot_keys_tenant_isolation")


def downgrade() -> None:
    for table_name, policy_name in (
        ("bot_keys", "bot_keys_tenant_isolation"),
        ("bots", "bots_tenant_isolation"),
    ):
        op.execute(sa.text(f"DROP POLICY IF EXISTS {policy_name} ON {table_name}"))
        op.execute(sa.text(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY"))

    op.drop_table("bot_keys")
    op.drop_table("bots")
