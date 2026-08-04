"""Create embedded document chunks and PostgreSQL lexical index.

Revision ID: 0007_document_chunks
Revises: 0006_knowledge_ingestion
Create Date: 2026-08-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0007_document_chunks"
down_revision: str | None = "0006_knowledge_ingestion"
branch_labels: tuple[str, ...] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("document_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("start_char", sa.Integer(), nullable=False),
        sa.Column("end_char", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(), nullable=False),
        sa.Column("embedding_provider", sa.String(length=100), nullable=False),
        sa.Column("embedding_model", sa.String(length=200), nullable=False),
        sa.Column("metadata", sa.JSON(), server_default="{}", nullable=False),
        sa.CheckConstraint(
            "length(content_checksum_sha256) = 64",
            name="ck_document_chunks_checksum_length",
        ),
        sa.CheckConstraint(
            "end_char > start_char",
            name="ck_document_chunks_offsets_valid",
        ),
        sa.CheckConstraint(
            "ordinal >= 0",
            name="ck_document_chunks_ordinal_nonnegative",
        ),
        sa.CheckConstraint(
            "start_char >= 0",
            name="ck_document_chunks_start_char_nonnegative",
        ),
        sa.CheckConstraint(
            "token_count > 0",
            name="ck_document_chunks_token_count_positive",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["documents.tenant_id", "documents.id"],
            name="fk_document_chunks_tenant_document_documents",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_chunks"),
        sa.UniqueConstraint(
            "tenant_id",
            "document_id",
            "ordinal",
            name="uq_document_chunks_tenant_document_ordinal",
        ),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.create_index("ix_document_chunks_tenant_id", "document_chunks", ["tenant_id"])
    op.create_index(
        "ix_document_chunks_tenant_document",
        "document_chunks",
        ["tenant_id", "document_id"],
    )
    op.execute(
        sa.text(
            """
            ALTER TABLE document_chunks
            ADD COLUMN search_vector tsvector
            GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED
            """
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX ix_document_chunks_search_vector "
            "ON document_chunks USING GIN (search_vector)"
        )
    )
    op.execute(sa.text("ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE document_chunks FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            """
            CREATE POLICY document_chunks_tenant_isolation
            ON document_chunks
            USING (
                tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            )
            WITH CHECK (
                tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            )
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DROP POLICY IF EXISTS document_chunks_tenant_isolation ON document_chunks"
        )
    )
    op.execute(sa.text("ALTER TABLE document_chunks NO FORCE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE document_chunks DISABLE ROW LEVEL SECURITY"))
    op.drop_table("document_chunks")
