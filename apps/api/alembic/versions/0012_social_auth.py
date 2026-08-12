"""Add provider identities for explicit social sign-in and linking.

Revision ID: 0012_social_auth
Revises: 0011_widget_configuration
Create Date: 2026-08-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0012_social_auth"
down_revision: str | None = "0011_widget_configuration"
branch_labels: tuple[str, ...] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.alter_column("users", "password_hash", existing_type=sa.Text(), nullable=True)
    op.create_table(
        "provider_identities",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("issuer", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("email_verified", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_provider_identities_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_provider_identities"),
        sa.UniqueConstraint(
            "provider",
            "issuer",
            "subject",
            name="uq_provider_identities_provider_issuer_subject",
        ),
        sa.UniqueConstraint(
            "user_id",
            "provider",
            name="uq_provider_identities_user_provider",
        ),
    )
    op.create_index("ix_provider_identities_user_id", "provider_identities", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_provider_identities_user_id", table_name="provider_identities")
    op.drop_table("provider_identities")
    op.alter_column("users", "password_hash", existing_type=sa.Text(), nullable=False)
