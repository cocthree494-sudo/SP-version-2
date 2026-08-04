"""Fail-closed tenant repositories for knowledge and ingestion state."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import (
    TenantContextError,
    get_current_tenant_id,
    maybe_current_tenant_id,
    set_database_tenant,
)
from app.db.base import utc_now
from app.domains.knowledge.enums import (
    TERMINAL_JOB_STATES,
    DocumentStatus,
    IngestionJobState,
    IngestionJobType,
    KnowledgeSourceStatus,
    KnowledgeSourceType,
)
from app.domains.knowledge.models import Document, DocumentChunk, IngestionJob, KnowledgeSource


class IdempotencyConflictError(RuntimeError):
    """Raised when one key is reused for a different logical operation."""


class _TenantKnowledgeRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID | None = None) -> None:
        self.session = session
        self._tenant_id = tenant_id

    def _resolve_tenant_id(self) -> UUID:
        context_tenant_id = maybe_current_tenant_id()
        if self._tenant_id is not None:
            if context_tenant_id is not None and context_tenant_id != self._tenant_id:
                raise TenantContextError("Repository tenant does not match active tenant context")
            return self._tenant_id
        return get_current_tenant_id()

    async def _prepare_scope(self) -> UUID:
        tenant_id = self._resolve_tenant_id()
        await set_database_tenant(self.session, tenant_id)
        return tenant_id


class KnowledgeSourceRepository(_TenantKnowledgeRepository):
    """Tenant-scoped source configuration and status persistence."""

    async def create(
        self,
        *,
        bot_id: UUID,
        source_type: KnowledgeSourceType,
        name: str,
        configuration: dict[str, Any] | None = None,
    ) -> KnowledgeSource:
        tenant_id = await self._prepare_scope()
        source = KnowledgeSource(
            tenant_id=tenant_id,
            bot_id=bot_id,
            type=source_type,
            name=name.strip(),
            configuration={} if configuration is None else configuration,
        )
        self.session.add(source)
        await self.session.flush()
        return source

    async def get(self, source_id: UUID) -> KnowledgeSource | None:
        tenant_id = await self._prepare_scope()
        return await self.session.scalar(
            select(KnowledgeSource).where(
                KnowledgeSource.id == source_id,
                KnowledgeSource.tenant_id == tenant_id,
            )
        )

    async def list_for_bot(self, bot_id: UUID) -> list[KnowledgeSource]:
        tenant_id = await self._prepare_scope()
        result = await self.session.scalars(
            select(KnowledgeSource)
            .where(
                KnowledgeSource.tenant_id == tenant_id,
                KnowledgeSource.bot_id == bot_id,
            )
            .order_by(KnowledgeSource.created_at, KnowledgeSource.id)
        )
        return list(result)

    async def set_status(
        self,
        source_id: UUID,
        status: KnowledgeSourceStatus,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> KnowledgeSource | None:
        source = await self.get(source_id)
        if source is None:
            return None
        source.status = status
        source.error_code = error_code
        source.error_message = error_message
        await self.session.flush()
        return source

    async def delete(self, source: KnowledgeSource) -> None:
        tenant_id = await self._prepare_scope()
        if source.tenant_id != tenant_id:
            raise TenantContextError("Cannot delete a source outside the active tenant")
        await self.session.delete(source)
        await self.session.flush()


class DocumentRepository(_TenantKnowledgeRepository):
    """Tenant-scoped document-version persistence."""

    async def create_next_version(
        self,
        *,
        source_id: UUID,
        document_key: str = "primary",
        checksum_sha256: str,
        title: str | None = None,
        canonical_url: str | None = None,
        raw_storage_key: str | None = None,
        normalized_storage_key: str | None = None,
        document_metadata: dict[str, Any] | None = None,
    ) -> Document:
        tenant_id = await self._prepare_scope()
        latest_version = await self.session.scalar(
            select(func.max(Document.version)).where(
                Document.tenant_id == tenant_id,
                Document.source_id == source_id,
                Document.document_key == document_key,
            )
        )
        document = Document(
            tenant_id=tenant_id,
            source_id=source_id,
            document_key=document_key,
            version=int(latest_version or 0) + 1,
            checksum_sha256=checksum_sha256.casefold(),
            title=title,
            canonical_url=canonical_url,
            raw_storage_key=raw_storage_key,
            normalized_storage_key=normalized_storage_key,
            document_metadata={} if document_metadata is None else document_metadata,
        )
        self.session.add(document)
        await self.session.flush()
        return document

    async def get(self, document_id: UUID) -> Document | None:
        tenant_id = await self._prepare_scope()
        return await self.session.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.tenant_id == tenant_id,
            )
        )

    async def get_active_for_source(
        self,
        source_id: UUID,
        *,
        document_key: str = "primary",
    ) -> Document | None:
        tenant_id = await self._prepare_scope()
        return await self.session.scalar(
            select(Document)
            .where(
                Document.tenant_id == tenant_id,
                Document.source_id == source_id,
                Document.document_key == document_key,
                Document.status == DocumentStatus.ACTIVE,
            )
            .order_by(Document.version.desc())
            .limit(1)
        )

    async def list_for_source(self, source_id: UUID) -> list[Document]:
        tenant_id = await self._prepare_scope()
        result = await self.session.scalars(
            select(Document)
            .where(
                Document.tenant_id == tenant_id,
                Document.source_id == source_id,
            )
            .order_by(Document.document_key, Document.version)
        )
        return list(result)

    async def activate(self, document: Document) -> None:
        tenant_id = await self._prepare_scope()
        if document.tenant_id != tenant_id:
            raise TenantContextError("Cannot activate a document outside the active tenant")
        active_documents = await self.session.scalars(
            select(Document).where(
                Document.tenant_id == tenant_id,
                Document.source_id == document.source_id,
                Document.document_key == document.document_key,
                Document.status == DocumentStatus.ACTIVE,
                Document.id != document.id,
            )
        )
        for active in active_documents:
            active.status = DocumentStatus.SUPERSEDED
        document.status = DocumentStatus.ACTIVE
        await self.session.flush()

    async def supersede_active_except(
        self,
        source_id: UUID,
        *,
        document_keys: set[str],
    ) -> None:
        tenant_id = await self._prepare_scope()
        query = select(Document).where(
            Document.tenant_id == tenant_id,
            Document.source_id == source_id,
            Document.status == DocumentStatus.ACTIVE,
        )
        if document_keys:
            query = query.where(Document.document_key.not_in(document_keys))
        active_documents = await self.session.scalars(query)
        for document in active_documents:
            document.status = DocumentStatus.SUPERSEDED
        await self.session.flush()


class IngestionJobRepository(_TenantKnowledgeRepository):
    """Idempotent job creation and explicit state transitions."""

    async def get(self, job_id: UUID, *, for_update: bool = False) -> IngestionJob | None:
        tenant_id = await self._prepare_scope()
        query = select(IngestionJob).where(
            IngestionJob.id == job_id,
            IngestionJob.tenant_id == tenant_id,
        )
        if for_update:
            query = query.with_for_update()
        return await self.session.scalar(query)

    async def get_by_idempotency_key(self, key: str) -> IngestionJob | None:
        tenant_id = await self._prepare_scope()
        return await self.session.scalar(
            select(IngestionJob).where(
                IngestionJob.tenant_id == tenant_id,
                IngestionJob.idempotency_key == key,
            )
        )

    @staticmethod
    def _ensure_idempotent_match(
        job: IngestionJob,
        *,
        source_id: UUID,
        job_type: IngestionJobType,
        payload: dict[str, Any],
    ) -> None:
        if job.source_id != source_id or job.type is not job_type or job.payload != payload:
            raise IdempotencyConflictError(
                "Idempotency key is already attached to another ingestion operation"
            )

    async def create_or_get(
        self,
        *,
        source_id: UUID,
        job_type: IngestionJobType,
        idempotency_key: str,
        payload: dict[str, Any] | None = None,
        max_attempts: int,
    ) -> tuple[IngestionJob, bool]:
        tenant_id = await self._prepare_scope()
        normalized_key = idempotency_key.strip()
        normalized_payload = {} if payload is None else payload
        existing = await self.get_by_idempotency_key(normalized_key)
        if existing is not None:
            self._ensure_idempotent_match(
                existing,
                source_id=source_id,
                job_type=job_type,
                payload=normalized_payload,
            )
            return existing, False

        job = IngestionJob(
            tenant_id=tenant_id,
            source_id=source_id,
            type=job_type,
            idempotency_key=normalized_key,
            payload=normalized_payload,
            max_attempts=max_attempts,
        )
        try:
            async with self.session.begin_nested():
                self.session.add(job)
                await self.session.flush()
        except IntegrityError:
            concurrent = await self.get_by_idempotency_key(normalized_key)
            if concurrent is None:
                raise
            self._ensure_idempotent_match(
                concurrent,
                source_id=source_id,
                job_type=job_type,
                payload=normalized_payload,
            )
            return concurrent, False
        return job, True

    async def claim(self, job_id: UUID, *, now: datetime | None = None) -> IngestionJob | None:
        current_time = utc_now() if now is None else now
        job = await self.get(job_id, for_update=True)
        if job is None or job.state in TERMINAL_JOB_STATES:
            return None
        if job.state is IngestionJobState.RUNNING:
            return None
        if job.scheduled_at is not None and job.scheduled_at > current_time:
            return None
        if job.attempts >= job.max_attempts:
            job.state = IngestionJobState.FAILED
            job.completed_at = current_time
            job.error_code = "attempts_exhausted"
            job.error_message = "Maximum ingestion attempts were exhausted"
            await self.session.flush()
            return None
        job.state = IngestionJobState.RUNNING
        job.attempts += 1
        job.started_at = current_time
        job.completed_at = None
        job.scheduled_at = None
        job.error_code = None
        job.error_message = None
        await self.session.flush()
        return job

    async def update_progress(self, job_id: UUID, progress_percent: int) -> IngestionJob | None:
        if not 0 <= progress_percent <= 100:
            raise ValueError("progress_percent must be between 0 and 100")
        job = await self.get(job_id, for_update=True)
        if job is None or job.state is not IngestionJobState.RUNNING:
            return None
        job.progress_percent = progress_percent
        await self.session.flush()
        return job

    async def mark_succeeded(
        self,
        job_id: UUID,
        *,
        now: datetime | None = None,
    ) -> IngestionJob | None:
        job = await self.get(job_id, for_update=True)
        if job is None or job.state in TERMINAL_JOB_STATES:
            return job
        job.state = IngestionJobState.SUCCEEDED
        job.progress_percent = 100
        job.completed_at = utc_now() if now is None else now
        job.scheduled_at = None
        job.error_code = None
        job.error_message = None
        await self.session.flush()
        return job

    async def mark_retry(
        self,
        job_id: UUID,
        *,
        error_code: str,
        error_message: str,
        scheduled_at: datetime,
    ) -> IngestionJob | None:
        job = await self.get(job_id, for_update=True)
        if job is None or job.state in TERMINAL_JOB_STATES:
            return job
        job.error_code = error_code[:100]
        job.error_message = error_message[:2000]
        if job.attempts >= job.max_attempts:
            job.state = IngestionJobState.FAILED
            job.completed_at = utc_now()
            job.scheduled_at = None
        else:
            job.state = IngestionJobState.RETRY_SCHEDULED
            job.scheduled_at = scheduled_at
        await self.session.flush()
        return job

    async def mark_failed(
        self,
        job_id: UUID,
        *,
        error_code: str,
        error_message: str,
        now: datetime | None = None,
    ) -> IngestionJob | None:
        job = await self.get(job_id, for_update=True)
        if job is None or job.state in TERMINAL_JOB_STATES:
            return job
        job.state = IngestionJobState.FAILED
        job.completed_at = utc_now() if now is None else now
        job.scheduled_at = None
        job.error_code = error_code[:100]
        job.error_message = error_message[:2000]
        await self.session.flush()
        return job

    async def list_dispatchable(self, *, limit: int = 100) -> list[IngestionJob]:
        tenant_id = await self._prepare_scope()
        now = utc_now()
        result = await self.session.scalars(
            select(IngestionJob)
            .where(
                IngestionJob.tenant_id == tenant_id,
                IngestionJob.state.in_(
                    [IngestionJobState.QUEUED, IngestionJobState.RETRY_SCHEDULED]
                ),
                (IngestionJob.scheduled_at.is_(None)) | (IngestionJob.scheduled_at <= now),
            )
            .order_by(IngestionJob.created_at, IngestionJob.id)
            .limit(limit)
        )
        return list(result)


class DocumentChunkRepository(_TenantKnowledgeRepository):
    """Tenant-scoped batch persistence for staged document chunks."""

    async def create_batch(
        self,
        *,
        document: Document,
        chunks: list[dict[str, Any]],
    ) -> list[DocumentChunk]:
        tenant_id = await self._prepare_scope()
        if document.tenant_id != tenant_id:
            raise TenantContextError("Cannot persist chunks outside the active tenant")
        records = [
            DocumentChunk(
                tenant_id=tenant_id,
                document_id=document.id,
                **chunk,
            )
            for chunk in chunks
        ]
        self.session.add_all(records)
        await self.session.flush()
        return records

    async def list_for_document(self, document_id: UUID) -> list[DocumentChunk]:
        tenant_id = await self._prepare_scope()
        result = await self.session.scalars(
            select(DocumentChunk)
            .where(
                DocumentChunk.tenant_id == tenant_id,
                DocumentChunk.document_id == document_id,
            )
            .order_by(DocumentChunk.ordinal)
        )
        return list(result)


__all__ = [
    "DocumentChunkRepository",
    "DocumentRepository",
    "IdempotencyConflictError",
    "IngestionJobRepository",
    "KnowledgeSourceRepository",
]
