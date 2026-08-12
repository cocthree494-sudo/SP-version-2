"""Add tenant-scoped channel installation metadata."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016_channel_installations"
down_revision = "0015_custom_provider_base_url"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channel_installations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("channel_type", sa.String(length=32), nullable=False),
        sa.Column("external_identity", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("conversation_scope", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("credential_reference", sa.Text(), nullable=True),
        sa.Column("consent_record", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(external_identity) BETWEEN 1 AND 255", name="ck_channel_identity"
        ),
        sa.CheckConstraint(
            "channel_type IN ('telegram_personal', 'whatsapp_business', 'facebook_page', 'email')",
            name="ck_channel_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'connected', 'paused', 'revoked', 'error')",
            name="ck_channel_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_channel_installations_tenant_id", "channel_installations", ["tenant_id"])
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE channel_installations TO support_agent_app"
    )


def downgrade() -> None:
    op.execute(
        "REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE channel_installations "
        "FROM support_agent_app"
    )
    op.drop_index("ix_channel_installations_tenant_id", table_name="channel_installations")
    op.drop_table("channel_installations")
