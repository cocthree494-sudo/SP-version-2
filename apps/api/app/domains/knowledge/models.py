"""Tenant-scoped knowledge, document-version, and ingestion-job models."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TenantScopedModel
from app.domains.knowledge.enums import (
    DocumentStatus,
    IngestionJobState,
    IngestionJobType,
    KnowledgeSourceStatus,
    KnowledgeSourceType,
)


def _enum_type(enum_class: type[Any], name: str, length: int) -> SqlEnum:
    return SqlEnum(
        enum_class,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=length,
        values_callable=lambda values: [item.value for item in values],
    )


class KnowledgeSource(TenantScopedModel):
    """One tenant-owned input configured for a bot."""

    __tablename__ = "knowledge_sources"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "bot_id"],
            ["bots.tenant_id", "bots.id"],
            name="fk_knowledge_sources_tenant_bot_bots",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_knowledge_sources_tenant_id_id",
        ),
        Index("ix_knowledge_sources_tenant_bot", "tenant_id", "bot_id"),
        CheckConstraint(
            "length(name) BETWEEN 1 AND 200",
            name="ck_knowledge_sources_name_length",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    bot_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    type: Mapped[KnowledgeSourceType] = mapped_column(
        _enum_type(KnowledgeSourceType, "knowledge_source_type", 16),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[KnowledgeSourceStatus] = mapped_column(
        _enum_type(KnowledgeSourceStatus, "knowledge_source_status", 16),
        default=KnowledgeSourceStatus.PENDING,
        server_default=KnowledgeSourceStatus.PENDING.value,
        nullable=False,
    )
    configuration: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        server_default="{}",
        nullable=False,
    )
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class Document(TenantScopedModel):
    """One immutable-by-convention version produced from a source."""

    __tablename__ = "documents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "source_id"],
            ["knowledge_sources.tenant_id", "knowledge_sources.id"],
            name="fk_documents_tenant_source_knowledge_sources",
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_documents_tenant_id_id"),
        UniqueConstraint(
            "tenant_id",
            "source_id",
            "document_key",
            "version",
            name="uq_documents_tenant_source_key_version",
        ),
        Index("ix_documents_tenant_source_status", "tenant_id", "source_id", "status"),
        CheckConstraint("version >= 1", name="ck_documents_version_positive"),
        CheckConstraint(
            "length(checksum_sha256) = 64",
            name="ck_documents_checksum_sha256_length",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    source_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    document_key: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    canonical_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        default=dict,
        server_default="{}",
        nullable=False,
    )
    status: Mapped[DocumentStatus] = mapped_column(
        _enum_type(DocumentStatus, "document_status", 16),
        default=DocumentStatus.STAGED,
        server_default=DocumentStatus.STAGED.value,
        nullable=False,
    )


class IngestionJob(TenantScopedModel):
    """Durable state for an idempotent background ingestion operation."""

    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "source_id"],
            ["knowledge_sources.tenant_id", "knowledge_sources.id"],
            name="fk_ingestion_jobs_tenant_source_knowledge_sources",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_ingestion_jobs_tenant_idempotency_key",
        ),
        Index("ix_ingestion_jobs_tenant_state_scheduled", "tenant_id", "state", "scheduled_at"),
        CheckConstraint("attempts >= 0", name="ck_ingestion_jobs_attempts_nonnegative"),
        CheckConstraint("max_attempts >= 1", name="ck_ingestion_jobs_max_attempts_positive"),
        CheckConstraint(
            "progress_percent BETWEEN 0 AND 100",
            name="ck_ingestion_jobs_progress_range",
        ),
        CheckConstraint(
            "length(idempotency_key) BETWEEN 1 AND 200",
            name="ck_ingestion_jobs_idempotency_key_length",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    source_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    type: Mapped[IngestionJobType] = mapped_column(
        _enum_type(IngestionJobType, "ingestion_job_type", 32),
        nullable=False,
    )
    state: Mapped[IngestionJobState] = mapped_column(
        _enum_type(IngestionJobState, "ingestion_job_state", 32),
        default=IngestionJobState.QUEUED,
        server_default=IngestionJobState.QUEUED.value,
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    progress_percent: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        server_default="{}",
        nullable=False,
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class DocumentChunk(TenantScopedModel):
    """Embedded retrieval unit belonging to one staged or active document."""

    __tablename__ = "document_chunks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["documents.tenant_id", "documents.id"],
            name="fk_document_chunks_tenant_document_documents",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "tenant_id",
            "document_id",
            "ordinal",
            name="uq_document_chunks_tenant_document_ordinal",
        ),
        Index("ix_document_chunks_tenant_document", "tenant_id", "document_id"),
        CheckConstraint("ordinal >= 0", name="ck_document_chunks_ordinal_nonnegative"),
        CheckConstraint("token_count > 0", name="ck_document_chunks_token_count_positive"),
        CheckConstraint("start_char >= 0", name="ck_document_chunks_start_char_nonnegative"),
        CheckConstraint("end_char > start_char", name="ck_document_chunks_offsets_valid"),
        CheckConstraint(
            "length(content_checksum_sha256) = 64",
            name="ck_document_chunks_checksum_length",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    document_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    start_char: Mapped[int] = mapped_column(Integer, nullable=False)
    end_char: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(), nullable=False)
    embedding_provider: Mapped[str] = mapped_column(String(100), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(200), nullable=False)
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        default=dict,
        server_default="{}",
        nullable=False,
    )


__all__ = ["Document", "DocumentChunk", "IngestionJob", "KnowledgeSource"]
