"""Create the restricted PostgreSQL application role used to prove RLS.

Revision ID: 0009_app_runtime_role
Revises: 0008_conversations
Create Date: 2026-08-04
"""

# ruff: noqa: S608 -- SQL identifiers are module constants, never user input.

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0009_app_runtime_role"
down_revision: str | None = "0008_conversations"
branch_labels: tuple[str, ...] | None = None
depends_on: str | None = None

_ROLE = "support_agent_app"
_APPLICATION_TABLES = (
    "users",
    "tenants",
    "tenant_memberships",
    "refresh_tokens",
    "bots",
    "bot_keys",
    "usage_events",
    "knowledge_sources",
    "documents",
    "ingestion_jobs",
    "document_chunks",
    "conversations",
    "messages",
)


def upgrade() -> None:
    """Create a non-owner login role and grant only application data access."""

    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{_ROLE}') THEN
                    CREATE ROLE {_ROLE}
                        LOGIN INHERIT
                        NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
                ELSE
                    ALTER ROLE {_ROLE}
                        LOGIN INHERIT
                        NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
                END IF;
            END
            $$
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                EXECUTE format(
                    'GRANT CONNECT ON DATABASE %I TO {_ROLE}',
                    current_database()
                );
            END
            $$
            """
        )
    )
    op.execute(sa.text(f"GRANT USAGE ON SCHEMA public TO {_ROLE}"))
    tables = ", ".join(_APPLICATION_TABLES)
    op.execute(
        sa.text(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {tables} TO {_ROLE}"
        )
    )


def downgrade() -> None:
    """Revoke this database's grants without dropping a cluster-wide role."""

    tables = ", ".join(_APPLICATION_TABLES)
    op.execute(
        sa.text(
            f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE {tables} FROM {_ROLE}"
        )
    )
    op.execute(sa.text(f"REVOKE USAGE ON SCHEMA public FROM {_ROLE}"))
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                EXECUTE format(
                    'REVOKE CONNECT ON DATABASE %I FROM {_ROLE}',
                    current_database()
                );
            END
            $$
            """
        )
    )
