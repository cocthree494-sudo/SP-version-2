"""Attach channel installations to the tenant bot that may answer them."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018_channel_bot_assignment"
down_revision = "0017_voice_agents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("channel_installations", sa.Column("bot_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_channel_installations_bot_id_bots",
        "channel_installations",
        "bots",
        ["bot_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_channel_installations_bot_id", "channel_installations", ["bot_id"])


def downgrade() -> None:
    op.drop_index("ix_channel_installations_bot_id", table_name="channel_installations")
    op.drop_constraint(
        "fk_channel_installations_bot_id_bots", "channel_installations", type_="foreignkey"
    )
    op.drop_column("channel_installations", "bot_id")
