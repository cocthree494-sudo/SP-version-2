"""Knowledge-source ingestion handlers executed only by the ARQ worker."""

from __future__ import annotations

import hashlib
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domains.knowledge.crawler import CrawlError, WebsiteCrawler
from app.domains.knowledge.embedding_pipeline import EmbeddingPipeline, EmbeddingPipelineError
from app.domains.knowledge.enums import KnowledgeSourceType
from app.domains.knowledge.extraction import TextExtractionError, extract_file
from app.domains.knowledge.files import FileKind
from app.domains.knowledge.manual import manual_document_text
from app.domains.knowledge.models import IngestionJob, KnowledgeSource
from app.domains.knowledge.repositories import (
    DocumentRepository,
    IngestionJobRepository,
    KnowledgeSourceRepository,
)
from app.providers.embeddings import EmbeddingProvider
from app.providers.storage import ObjectStorage
from app.workers.ingestion import PermanentIngestionError, RetryableIngestionError


async def read_stored_bytes(
    storage: ObjectStorage,
    *,
    tenant_id: UUID,
    key: str,
    max_bytes: int,
) -> bytes:
    content = bytearray()
    try:
        async for chunk in storage.read_stream(tenant_id, key):
            content.extend(chunk)
            if len(content) > max_bytes:
                raise PermanentIngestionError(
                    "stored_file_too_large",
                    "Stored file exceeds the processing limit",
                )
    except FileNotFoundError as exc:
        raise PermanentIngestionError(
            "stored_file_missing",
            "The uploaded file is missing from storage",
        ) from exc
    except PermanentIngestionError:
        raise
    except OSError as exc:
        raise RetryableIngestionError(
            "storage_unavailable",
            "Object storage is temporarily unavailable",
        ) from exc
    return bytes(content)


class SourceIngestionHandler:
    """Dispatch source types while sharing one job type and transaction."""

    def __init__(self, storage: ObjectStorage, embedding_provider: EmbeddingProvider) -> None:
        self.storage = storage
        self.embedding_provider = embedding_provider

    async def __call__(self, session: AsyncSession, job: IngestionJob) -> None:
        source = await KnowledgeSourceRepository(session, job.tenant_id).get(job.source_id)
        if source is None:
            raise PermanentIngestionError("source_missing", "Knowledge source no longer exists")
        if source.type is KnowledgeSourceType.FILE:
            await self._ingest_file(session, source)
            return
        if source.type is KnowledgeSourceType.WEBSITE:
            await self._ingest_website(session, source, job)
            return
        if source.type is KnowledgeSourceType.MANUAL:
            await self._ingest_manual(session, source)
            return
        raise PermanentIngestionError(
            "source_type_not_supported",
            f"Ingestion is not configured for {source.type.value} sources",
        )

    async def _ingest_file(self, session: AsyncSession, source: KnowledgeSource) -> None:
        storage_key = source.configuration.get("storage_key")
        filename = source.configuration.get("original_filename")
        file_kind = source.configuration.get("file_kind")
        checksum = source.configuration.get("checksum_sha256")
        if (
            not isinstance(storage_key, str)
            or not isinstance(filename, str)
            or not isinstance(file_kind, str)
            or not isinstance(checksum, str)
        ):
            raise PermanentIngestionError(
                "invalid_file_configuration",
                "File source configuration is incomplete",
            )
        try:
            kind = FileKind(file_kind)
        except ValueError as exc:
            raise PermanentIngestionError(
                "unsupported_file_type",
                "The stored file type is unsupported",
            ) from exc
        documents = DocumentRepository(session, source.tenant_id)
        active = await documents.get_active_for_source(source.id)
        if active is not None and active.checksum_sha256 == checksum:
            return

        data = await read_stored_bytes(
            self.storage,
            tenant_id=source.tenant_id,
            key=storage_key,
            max_bytes=settings.FILE_UPLOAD_MAX_BYTES,
        )
        try:
            extracted = extract_file(data, kind=kind, filename=filename)
        except TextExtractionError as exc:
            raise PermanentIngestionError(exc.code, str(exc)) from exc

        normalized_bytes = extracted.text.encode("utf-8")
        normalized_checksum = hashlib.sha256(normalized_bytes).hexdigest()
        normalized_key = f"sources/{source.id}/normalized/{checksum}.txt"
        try:
            await self.storage.put_stream(
                source.tenant_id,
                normalized_key,
                _single_chunk(normalized_bytes),
            )
        except OSError as exc:
            raise RetryableIngestionError(
                "storage_unavailable",
                "Object storage is temporarily unavailable",
            ) from exc

        document = await documents.create_next_version(
            source_id=source.id,
            checksum_sha256=checksum,
            title=extracted.title or filename,
            raw_storage_key=storage_key,
            normalized_storage_key=normalized_key,
            document_metadata={
                **extracted.metadata,
                "normalized_checksum_sha256": normalized_checksum,
                "original_filename": filename,
            },
        )
        try:
            await EmbeddingPipeline(
                session,
                source.tenant_id,
                self.embedding_provider,
            ).run(document, extracted.text)
        except EmbeddingPipelineError as exc:
            error_type = RetryableIngestionError if exc.retryable else PermanentIngestionError
            raise error_type(exc.code, str(exc)) from exc
        await documents.activate(document)

    async def _ingest_website(
        self,
        session: AsyncSession,
        source: KnowledgeSource,
        job: IngestionJob,
    ) -> None:
        start_url = source.configuration.get("start_url")
        max_pages = source.configuration.get("max_pages")
        max_depth = source.configuration.get("max_depth")
        request_delay = source.configuration.get("request_delay_seconds")
        if (
            not isinstance(start_url, str)
            or not isinstance(max_pages, int)
            or not isinstance(max_depth, int)
            or not isinstance(request_delay, (int, float))
        ):
            raise PermanentIngestionError(
                "invalid_website_configuration",
                "Website source configuration is incomplete",
            )

        jobs = IngestionJobRepository(session, source.tenant_id)

        async def progress(completed: int, total: int) -> None:
            await jobs.update_progress(job.id, min(int(completed / total * 90), 90))

        try:
            async with httpx.AsyncClient(
                timeout=settings.WEBSITE_CRAWL_TIMEOUT_SECONDS,
                max_redirects=settings.WEBSITE_CRAWL_MAX_REDIRECTS,
            ) as client:
                pages = await WebsiteCrawler(client).crawl(
                    start_url,
                    max_pages=min(max_pages, settings.WEBSITE_CRAWL_MAX_PAGES),
                    max_depth=min(max_depth, settings.WEBSITE_CRAWL_MAX_DEPTH),
                    request_delay_seconds=float(request_delay),
                    progress=progress,
                )
        except CrawlError as exc:
            error_type = RetryableIngestionError if exc.retryable else PermanentIngestionError
            raise error_type(exc.code, str(exc)) from exc

        documents = DocumentRepository(session, source.tenant_id)
        active_keys: set[str] = set()
        for page in pages:
            document_key = hashlib.sha256(page.url.encode("utf-8")).hexdigest()
            active_keys.add(document_key)
            active = await documents.get_active_for_source(
                source.id,
                document_key=document_key,
            )
            if active is not None and active.checksum_sha256 == page.checksum_sha256:
                continue
            normalized_key = (
                f"sources/{source.id}/web/{document_key}/{page.checksum_sha256}.txt"
            )
            try:
                await self.storage.put_stream(
                    source.tenant_id,
                    normalized_key,
                    _single_chunk(page.text.encode("utf-8")),
                )
            except OSError as exc:
                raise RetryableIngestionError(
                    "storage_unavailable",
                    "Object storage is temporarily unavailable",
                ) from exc
            document = await documents.create_next_version(
                source_id=source.id,
                document_key=document_key,
                checksum_sha256=page.checksum_sha256,
                title=page.title,
                canonical_url=page.url,
                normalized_storage_key=normalized_key,
                document_metadata={"format": "webpage"},
            )
            try:
                await EmbeddingPipeline(
                    session,
                    source.tenant_id,
                    self.embedding_provider,
                ).run(document, page.text)
            except EmbeddingPipelineError as exc:
                error_type = RetryableIngestionError if exc.retryable else PermanentIngestionError
                raise error_type(exc.code, str(exc)) from exc
            await documents.activate(document)
        await documents.supersede_active_except(source.id, document_keys=active_keys)

    async def _ingest_manual(self, session: AsyncSession, source: KnowledgeSource) -> None:
        question = source.configuration.get("question")
        answer = source.configuration.get("answer")
        checksum = source.configuration.get("checksum_sha256")
        if (
            not isinstance(question, str)
            or not isinstance(answer, str)
            or not isinstance(checksum, str)
        ):
            raise PermanentIngestionError(
                "invalid_manual_configuration",
                "Manual source configuration is incomplete",
            )
        documents = DocumentRepository(session, source.tenant_id)
        active = await documents.get_active_for_source(source.id)
        if active is not None and active.checksum_sha256 == checksum:
            return
        text = manual_document_text(question, answer)
        normalized_key = f"sources/{source.id}/manual/{checksum}.txt"
        try:
            await self.storage.put_stream(
                source.tenant_id,
                normalized_key,
                _single_chunk(text.encode("utf-8")),
            )
        except OSError as exc:
            raise RetryableIngestionError(
                "storage_unavailable",
                "Object storage is temporarily unavailable",
            ) from exc
        document = await documents.create_next_version(
            source_id=source.id,
            checksum_sha256=checksum,
            title=question[:500],
            normalized_storage_key=normalized_key,
            document_metadata={"format": "manual_qa", "authoritative": True},
        )
        try:
            await EmbeddingPipeline(
                session,
                source.tenant_id,
                self.embedding_provider,
            ).run(document, text)
        except EmbeddingPipelineError as exc:
            error_type = RetryableIngestionError if exc.retryable else PermanentIngestionError
            raise error_type(exc.code, str(exc)) from exc
        await documents.activate(document)


async def _single_chunk(content: bytes):  # type: ignore[no-untyped-def]
    yield content


__all__ = ["SourceIngestionHandler", "read_stored_bytes"]
