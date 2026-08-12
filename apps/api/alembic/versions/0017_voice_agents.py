"""Add tenant-scoped voice-agent configuration and webhook idempotency."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017_voice_agents"
down_revision = "0016_channel_installations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "voice_agent_installations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("bot_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=32), server_default="twilio", nullable=False),
        sa.Column("phone_number", sa.String(length=32), nullable=False),
        sa.Column("language", sa.String(length=16), server_default="auto", nullable=False),
        sa.Column("voice", sa.String(length=64), server_default="alloy", nullable=False),
        sa.Column("business_hours", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("outbound_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("recording_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("retention_days", sa.Integer(), server_default="0", nullable=False),
        sa.Column("monthly_cost_limit_usd", sa.Integer(), server_default="100", nullable=False),
        sa.Column("provider_reference", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.CheckConstraint("length(phone_number) BETWEEN 3 AND 32", name="ck_voice_phone_length"),
        sa.CheckConstraint("retention_days BETWEEN 0 AND 365", name="ck_voice_retention_days"),
        sa.CheckConstraint(
            "monthly_cost_limit_usd BETWEEN 1 AND 100000", name="ck_voice_cost_limit"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'ready', 'paused', 'error')", name="ck_voice_status"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["bot_id"], ["bots.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "phone_number", name="uq_voice_tenant_phone"),
    )
    op.create_index(
        "ix_voice_agent_installations_tenant_id", "voice_agent_installations", ["tenant_id"]
    )
    op.create_index("ix_voice_agent_installations_bot_id", "voice_agent_installations", ["bot_id"])
    op.create_table(
        "voice_webhook_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["installation_id"], ["voice_agent_installations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "event_id", name="uq_voice_webhook_event"),
    )
    op.create_index("ix_voice_webhook_events_tenant_id", "voice_webhook_events", ["tenant_id"])
    op.create_index(
        "ix_voice_webhook_events_installation_id", "voice_webhook_events", ["installation_id"]
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE voice_agent_installations, "
        "voice_webhook_events TO support_agent_app"
    )


def downgrade() -> None:
    op.execute(
        "REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE voice_agent_installations, "
        "voice_webhook_events FROM support_agent_app"
    )
    op.drop_index("ix_voice_webhook_events_installation_id", table_name="voice_webhook_events")
    op.drop_index("ix_voice_webhook_events_tenant_id", table_name="voice_webhook_events")
    op.drop_table("voice_webhook_events")
    op.drop_index("ix_voice_agent_installations_bot_id", table_name="voice_agent_installations")
    op.drop_index("ix_voice_agent_installations_tenant_id", table_name="voice_agent_installations")
    op.drop_table("voice_agent_installations")
