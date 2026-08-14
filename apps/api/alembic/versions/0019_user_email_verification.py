"""Record when a Relay account email was verified by OTP."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019_user_email_verification"
down_revision = "0018_channel_bot_assignment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "email_verified_at")
