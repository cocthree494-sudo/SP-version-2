"""Create tenant-owned conversations and ordered messages.

Revision ID: 0008_conversations
Revises: 0007_document_chunks
Create Date: 2026-08-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0008_conversations"
down_revision: str | None = "0007_document_chunks"
branch_labels: tuple[str, ...] | None = None
depends_on: str | None = None


def _force_tenant_rls(table: str, policy: str) -> None:
    op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            f"""
            CREATE POLICY {policy}
            ON {table}
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
        "conversations",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("bot_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=200), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="active",
            nullable=False,
        ),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "summary_through_sequence",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "next_message_sequence",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
        sa.Column("retention_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(channel) BETWEEN 1 AND 32",
            name="ck_conversations_channel_length",
        ),
        sa.CheckConstraint(
            "external_id IS NULL OR length(external_id) BETWEEN 1 AND 200",
            name="ck_conversations_external_id_length",
        ),
        sa.CheckConstraint(
            "next_message_sequence >= 1",
            name="ck_conversations_next_sequence_positive",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'closed')",
            name="ck_conversations_status",
        ),
        sa.CheckConstraint(
            "summary_through_sequence >= 0",
            name="ck_conversations_summary_sequence_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "bot_id"],
            ["bots.tenant_id", "bots.id"],
            name="fk_conversations_tenant_bot_bots",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_conversations"),
        sa.UniqueConstraint(
            "tenant_id",
            "bot_id",
            "channel",
            "external_id",
            name="uq_conversations_tenant_bot_channel_external",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_conversations_tenant_id_id"),
    )
    op.create_index("ix_conversations_bot_id", "conversations", ["bot_id"])
    op.create_index("ix_conversations_tenant_id", "conversations", ["tenant_id"])
    op.create_index(
        "ix_conversations_tenant_bot_updated",
        "conversations",
        ["tenant_id", "bot_id", "updated_at"],
    )
    op.create_index(
        "ix_conversations_tenant_retention",
        "conversations",
        ["tenant_id", "retention_expires_at"],
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("conversation_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("metadata", sa.JSON(), server_default="{}", nullable=False),
        sa.CheckConstraint(
            "length(content) >= 1",
            name="ck_messages_content_nonempty",
        ),
        sa.CheckConstraint(
            "role IN ('user', 'assistant', 'system', 'tool')",
            name="ck_messages_role",
        ),
        sa.CheckConstraint("sequence >= 1", name="ck_messages_sequence_positive"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            name="fk_messages_tenant_conversation_conversations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_messages"),
        sa.UniqueConstraint(
            "tenant_id",
            "conversation_id",
            "sequence",
            name="uq_messages_tenant_conversation_sequence",
        ),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index("ix_messages_tenant_id", "messages", ["tenant_id"])
    op.create_index(
        "ix_messages_tenant_conversation_created",
        "messages",
        ["tenant_id", "conversation_id", "created_at"],
    )
    _force_tenant_rls("conversations", "conversations_tenant_isolation")
    _force_tenant_rls("messages", "messages_tenant_isolation")


def downgrade() -> None:
    for table in ("messages", "conversations"):
        op.execute(sa.text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
        op.execute(sa.text(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))
    op.drop_table("messages")
    op.drop_table("conversations")
