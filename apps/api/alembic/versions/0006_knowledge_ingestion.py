"""Create knowledge sources, document versions, and ingestion jobs.

Revision ID: 0006_knowledge_ingestion
Revises: 0005_usage
Create Date: 2026-08-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0006_knowledge_ingestion"
down_revision: str | None = "0005_usage"
branch_labels: tuple[str, ...] | None = None
depends_on: str | None = None


def _enum(name: str, *values: str, length: int) -> sa.Enum:
    return sa.Enum(
        *values,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=length,
    )


def _enable_tenant_rls(table_name: str, policy_name: str) -> None:
    op.execute(sa.text(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            f"""
            CREATE POLICY {policy_name}
            ON {table_name}
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
        "knowledge_sources",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("bot_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "type",
            _enum(
                "knowledge_source_type",
                "file",
                "website",
                "manual",
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "status",
            _enum(
                "knowledge_source_status",
                "pending",
                "processing",
                "ready",
                "failed",
                "deleting",
                length=16,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("configuration", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "length(name) BETWEEN 1 AND 200",
            name="ck_knowledge_sources_name_length",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "bot_id"],
            ["bots.tenant_id", "bots.id"],
            name="fk_knowledge_sources_tenant_bot_bots",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_sources"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_knowledge_sources_tenant_id_id",
        ),
    )
    op.create_index("ix_knowledge_sources_bot_id", "knowledge_sources", ["bot_id"])
    op.create_index("ix_knowledge_sources_tenant_id", "knowledge_sources", ["tenant_id"])
    op.create_index(
        "ix_knowledge_sources_tenant_bot",
        "knowledge_sources",
        ["tenant_id", "bot_id"],
    )

    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("source_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("document_key", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("canonical_url", sa.Text(), nullable=True),
        sa.Column("raw_storage_key", sa.Text(), nullable=True),
        sa.Column("normalized_storage_key", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), server_default="{}", nullable=False),
        sa.Column(
            "status",
            _enum(
                "document_status",
                "staged",
                "active",
                "superseded",
                "failed",
                length=16,
            ),
            server_default="staged",
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(checksum_sha256) = 64",
            name="ck_documents_checksum_sha256_length",
        ),
        sa.CheckConstraint("version >= 1", name="ck_documents_version_positive"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_id"],
            ["knowledge_sources.tenant_id", "knowledge_sources.id"],
            name="fk_documents_tenant_source_knowledge_sources",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_documents"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_documents_tenant_id_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "source_id",
            "document_key",
            "version",
            name="uq_documents_tenant_source_key_version",
        ),
    )
    op.create_index("ix_documents_source_id", "documents", ["source_id"])
    op.create_index("ix_documents_tenant_id", "documents", ["tenant_id"])
    op.create_index(
        "ix_documents_tenant_source_status",
        "documents",
        ["tenant_id", "source_id", "status"],
    )

    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("source_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "type",
            _enum(
                "ingestion_job_type",
                "ingest_source",
                "delete_source",
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "state",
            _enum(
                "ingestion_job_state",
                "queued",
                "running",
                "retry_scheduled",
                "succeeded",
                "failed",
                "cancelled",
                length=32,
            ),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("progress_percent", sa.Integer(), server_default="0", nullable=False),
        sa.Column("payload", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "attempts >= 0",
            name="ck_ingestion_jobs_attempts_nonnegative",
        ),
        sa.CheckConstraint(
            "length(idempotency_key) BETWEEN 1 AND 200",
            name="ck_ingestion_jobs_idempotency_key_length",
        ),
        sa.CheckConstraint(
            "max_attempts >= 1",
            name="ck_ingestion_jobs_max_attempts_positive",
        ),
        sa.CheckConstraint(
            "progress_percent BETWEEN 0 AND 100",
            name="ck_ingestion_jobs_progress_range",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_id"],
            ["knowledge_sources.tenant_id", "knowledge_sources.id"],
            name="fk_ingestion_jobs_tenant_source_knowledge_sources",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ingestion_jobs"),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_ingestion_jobs_tenant_idempotency_key",
        ),
    )
    op.create_index("ix_ingestion_jobs_source_id", "ingestion_jobs", ["source_id"])
    op.create_index("ix_ingestion_jobs_tenant_id", "ingestion_jobs", ["tenant_id"])
    op.create_index(
        "ix_ingestion_jobs_tenant_state_scheduled",
        "ingestion_jobs",
        ["tenant_id", "state", "scheduled_at"],
    )

    _enable_tenant_rls("knowledge_sources", "knowledge_sources_tenant_isolation")
    _enable_tenant_rls("documents", "documents_tenant_isolation")
    _enable_tenant_rls("ingestion_jobs", "ingestion_jobs_tenant_isolation")


def downgrade() -> None:
    for table_name, policy_name in (
        ("ingestion_jobs", "ingestion_jobs_tenant_isolation"),
        ("documents", "documents_tenant_isolation"),
        ("knowledge_sources", "knowledge_sources_tenant_isolation"),
    ):
        op.execute(sa.text(f"DROP POLICY IF EXISTS {policy_name} ON {table_name}"))
        op.execute(sa.text(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY"))

    op.drop_table("ingestion_jobs")
    op.drop_table("documents")
    op.drop_table("knowledge_sources")
