"""Store verified custom provider endpoint URLs."""

from alembic import op
import sqlalchemy as sa

revision = "0015_custom_provider_base_url"
down_revision = "0014_provider_catalog_values"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("provider_credentials", sa.Column("base_url", sa.String(length=2048), nullable=True))


def downgrade() -> None:
    op.drop_column("provider_credentials", "base_url")
