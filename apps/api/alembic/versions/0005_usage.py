"""Create immutable tenant usage events.

Revision ID: 0005_usage
Revises: 0004_bots
Create Date: 2026-08-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0005_usage"
down_revision: str | None = "0004_bots"
branch_labels: tuple[str, ...] | None = None
depends_on: str | None = None


def _usage_operation() -> sa.Enum:
    return sa.Enum(
        "generation",
        "embedding",
        name="usage_operation",
        native_enum=False,
        create_constraint=True,
        length=16,
    )


def upgrade() -> None:
    op.create_table(
        "usage_events",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("bot_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("conversation_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("operation", _usage_operation(), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("input_tokens", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("cache_read_tokens", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("cache_write_tokens", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("latency_ms", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "estimated_cost_microusd",
            sa.BigInteger(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "cache_read_tokens >= 0",
            name="ck_usage_cache_read_tokens_nonnegative",
        ),
        sa.CheckConstraint(
            "cache_write_tokens >= 0",
            name="ck_usage_cache_write_tokens_nonnegative",
        ),
        sa.CheckConstraint(
            "estimated_cost_microusd >= 0",
            name="ck_usage_estimated_cost_nonnegative",
        ),
        sa.CheckConstraint("input_tokens >= 0", name="ck_usage_input_tokens_nonnegative"),
        sa.CheckConstraint("latency_ms >= 0", name="ck_usage_latency_ms_nonnegative"),
        sa.CheckConstraint("length(model) BETWEEN 1 AND 200", name="ck_usage_model_length"),
        sa.CheckConstraint("output_tokens >= 0", name="ck_usage_output_tokens_nonnegative"),
        sa.CheckConstraint(
            "length(provider) BETWEEN 1 AND 100",
            name="ck_usage_provider_length",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_usage_events_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_usage_events"),
    )
    op.create_index("ix_usage_events_bot_id", "usage_events", ["bot_id"])
    op.create_index("ix_usage_events_conversation_id", "usage_events", ["conversation_id"])
    op.create_index("ix_usage_events_tenant_id", "usage_events", ["tenant_id"])
    op.create_index(
        "ix_usage_events_tenant_bot_created",
        "usage_events",
        ["tenant_id", "bot_id", "created_at"],
    )
    op.create_index(
        "ix_usage_events_tenant_created",
        "usage_events",
        ["tenant_id", "created_at"],
    )

    op.execute(sa.text("ALTER TABLE usage_events ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE usage_events FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            """
            CREATE POLICY usage_events_tenant_isolation
            ON usage_events
            USING (
                tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            )
            WITH CHECK (
                tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            )
            """
        )
    )

    op.execute(
        sa.text(
            """
            CREATE FUNCTION prevent_usage_events_mutation()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION 'usage_events is append-only' USING ERRCODE = '55000';
            END;
            $$
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER usage_events_prevent_mutation
            BEFORE UPDATE OR DELETE ON usage_events
            FOR EACH ROW EXECUTE FUNCTION prevent_usage_events_mutation()
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP TRIGGER IF EXISTS usage_events_prevent_mutation ON usage_events"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_usage_events_mutation()"))
    op.execute(sa.text("DROP POLICY IF EXISTS usage_events_tenant_isolation ON usage_events"))
    op.execute(sa.text("ALTER TABLE usage_events NO FORCE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE usage_events DISABLE ROW LEVEL SECURITY"))
    op.drop_table("usage_events")
