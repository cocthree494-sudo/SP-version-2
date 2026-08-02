"""Enable pgvector for tenant-scoped document embeddings.

Revision ID: 0001_enable_pgvector
Revises:
Create Date: 2026-08-03
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0001_enable_pgvector"
down_revision: str | None = None
branch_labels: tuple[str, ...] | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Install the vector data type supplied by the pgvector image."""

    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))


def downgrade() -> None:
    """Remove the extension when rolling back the initial schema revision."""

    op.execute(sa.text("DROP EXTENSION IF EXISTS vector"))
