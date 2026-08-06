"""Create encrypted tenant provider credentials and routing policies.

Revision ID: 0010_provider_access
Revises: 0009_app_runtime_role
Create Date: 2026-08-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0010_provider_access"
down_revision: str | None = "0009_app_runtime_role"
branch_labels: tuple[str, ...] | None = None
depends_on: str | None = None

_RUNTIME_ROLE = "support_agent_app"
_TENANT_POLICIES = {
    "provider_credentials": "provider_credentials_tenant_isolation",
    "provider_policies": "provider_policies_tenant_isolation",
}
_TABLES = tuple(_TENANT_POLICIES)


def _enum(name: str, *values: str, length: int) -> sa.Enum:
    return sa.Enum(
        *values,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=length,
    )


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
        "provider_credentials",
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
        sa.Column(
            "provider",
            _enum("generation_provider", "openai", length=32),
            nullable=False,
        ),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("encrypted_secret", sa.Text(), nullable=False),
        sa.Column("wrapped_data_key", sa.Text(), nullable=False),
        sa.Column("key_version", sa.String(length=64), nullable=False),
        sa.Column("masked_secret", sa.String(length=32), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("low_cost_model_id", sa.String(length=200), nullable=False),
        sa.Column("strong_model_id", sa.String(length=200), nullable=True),
        sa.Column(
            "status",
            _enum(
                "provider_credential_status",
                "unverified",
                "verified",
                "invalid",
                "revoked",
                length=16,
            ),
            server_default="unverified",
            nullable=False,
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(label) BETWEEN 1 AND 100",
            name="ck_provider_credentials_label",
        ),
        sa.CheckConstraint(
            "length(low_cost_model_id) BETWEEN 1 AND 200",
            name="ck_provider_credentials_low_model",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_provider_credentials_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_provider_credentials"),
        sa.UniqueConstraint(
            "tenant_id",
            "fingerprint",
            name="uq_provider_credentials_tenant_fingerprint",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_provider_credentials_tenant_id_id",
        ),
    )
    op.create_index(
        "ix_provider_credentials_tenant_id",
        "provider_credentials",
        ["tenant_id"],
    )

    op.create_table(
        "provider_policies",
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
        sa.Column(
            "mode",
            _enum(
                "provider_routing_mode",
                "platform_only",
                "tenant_first_with_platform_fallback",
                "tenant_only",
                length=48,
            ),
            server_default="platform_only",
            nullable=False,
        ),
        sa.Column("credential_order", sa.JSON(), server_default="[]", nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_provider_policies_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_provider_policies"),
        sa.UniqueConstraint("tenant_id", name="uq_provider_policies_tenant_id"),
    )
    op.create_index(
        "ix_provider_policies_tenant_id",
        "provider_policies",
        ["tenant_id"],
    )

    for table, policy in _TENANT_POLICIES.items():
        _force_tenant_rls(table, policy)
    op.execute(
        sa.text(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "
            f"{', '.join(_TABLES)} TO {_RUNTIME_ROLE}"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE "
            f"{', '.join(_TABLES)} FROM {_RUNTIME_ROLE}"
        )
    )
    for table in reversed(_TABLES):
        op.execute(sa.text(f"DROP POLICY IF EXISTS {_TENANT_POLICIES[table]} ON {table}"))
        op.execute(sa.text(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))
        op.drop_table(table)
