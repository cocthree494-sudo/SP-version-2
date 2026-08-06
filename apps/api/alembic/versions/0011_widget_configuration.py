"""Persist basic widget appearance configuration on bots.

Revision ID: 0011_widget_configuration
Revises: 0010_provider_access
Create Date: 2026-08-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0011_widget_configuration"
down_revision: str | None = "0010_provider_access"
branch_labels: tuple[str, ...] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "bots",
        sa.Column(
            "widget_welcome_text",
            sa.String(length=160),
            server_default="How can we help?",
            nullable=False,
        ),
    )
    op.add_column(
        "bots",
        sa.Column(
            "widget_accent_color",
            sa.String(length=7),
            server_default="#194f46",
            nullable=False,
        ),
    )
    op.add_column(
        "bots",
        sa.Column(
            "widget_position",
            sa.String(length=5),
            server_default="right",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_bots_widget_welcome_length",
        "bots",
        "length(widget_welcome_text) BETWEEN 1 AND 160",
    )
    op.create_check_constraint(
        "ck_bots_widget_accent_hex",
        "bots",
        "length(widget_accent_color) = 7 "
        "AND substr(widget_accent_color, 1, 1) = '#'",
    )
    op.create_check_constraint(
        "ck_bots_widget_position",
        "bots",
        "widget_position IN ('left', 'right')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_bots_widget_position", "bots", type_="check")
    op.drop_constraint("ck_bots_widget_accent_hex", "bots", type_="check")
    op.drop_constraint("ck_bots_widget_welcome_length", "bots", type_="check")
    op.drop_column("bots", "widget_position")
    op.drop_column("bots", "widget_accent_color")
    op.drop_column("bots", "widget_welcome_text")
