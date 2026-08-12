"""Grant the restricted runtime role access to social-auth identities.

Revision ID: 0013_grant_provider_identities_runtime_role
Revises: 0012_social_auth
Create Date: 2026-08-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0013_grant_provider_identities_runtime_role"
down_revision: str | None = "0012_social_auth"
branch_labels: tuple[str, ...] | None = None
depends_on: str | None = None

_RUNTIME_ROLE = "support_agent_app"
_TABLE = "provider_identities"


def upgrade() -> None:
    op.execute(
        sa.text(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {_TABLE} TO {_RUNTIME_ROLE}"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE {_TABLE} FROM {_RUNTIME_ROLE}"
        )
    )
