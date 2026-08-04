"""Secure streaming file-source validation, persistence, and cleanup."""

from __future__ import annotations

import codecs
import re
import unicodedata
from collections.abc import AsyncIterator
from enum import StrEnum
from pathlib import PurePath
from typing import Protocol
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domains.bots.repositories import BotRepository
from app.domains.knowledge.enums import (
    IngestionJobType,
    KnowledgeSourceStatus,
    KnowledgeSourceType,
)
from app.domains.knowledge.models import KnowledgeSource
from app.domains.knowledge.repositories import (
    DocumentRepository,
    IngestionJobRepository,
    KnowledgeSourceRepository,
)
from app.providers.storage import ObjectStorage
from app.workers.queue import IngestionQueue, IngestionQueueMessage

logger = structlog.get_logger(__name__)


class FileKind(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    TEXT = "txt"
    MARKDOWN = "md"


class FileUploadError(ValueError):
    """A safe validation error suitable for an API response."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class FileTooLargeError(FileUploadError):
    """Raised as soon as a streaming upload crosses its configured limit."""


class UploadReader(Protocol):
    filename: str | None
    content_type: str | None

    async def read(self, size: int = -1) -> bytes: ...


_EXTENSION_KINDS = {
    ".pdf": FileKind.PDF,
    ".docx": FileKind.DOCX,
    ".txt": FileKind.TEXT,
    ".md": FileKind.MARKDOWN,
    ".markdown": FileKind.MARKDOWN,
}
_ALLOWED_MEDIA_TYPES = {
    FileKind.PDF: {"application/pdf", "application/octet-stream"},
    FileKind.DOCX: {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
        "application/octet-stream",
    },
    FileKind.TEXT: {"text/plain", "application/octet-stream"},
    FileKind.MARKDOWN: {
        "text/markdown",
        "text/plain",
        "application/octet-stream",
    },
}


def sanitize_upload_filename(filename: str | None) -> str:
    """Keep a display-only basename without trusting it as a storage path."""

    if filename is None:
        raise FileUploadError("filename_required", "A filename is required")
    basename = re.split(r"[/\\]", filename)[-1]
    normalized = unicodedata.normalize("NFKC", basename)
    cleaned = "".join(character for character in normalized if ord(character) >= 32).strip()
    if not cleaned or cleaned in {".", ".."}:
        raise FileUploadError("invalid_filename", "The filename is invalid")
    return cleaned[:255]


def classify_upload(filename: str, content_type: str | None) -> FileKind:
    extension = PurePath(filename).suffix.casefold()
    kind = _EXTENSION_KINDS.get(extension)
    if kind is None:
        raise FileUploadError(
            "unsupported_extension",
            "Only PDF, DOCX, TXT, and Markdown files are supported",
        )
    declared_type = (
        (content_type or "application/octet-stream").partition(";")[0].strip().casefold()
    )
    if declared_type not in _ALLOWED_MEDIA_TYPES[kind]:
        raise FileUploadError(
            "content_type_mismatch",
            "The declared content type does not match the file extension",
        )
    return kind


def _validate_signature(kind: FileKind, sample: bytes) -> None:
    if kind is FileKind.PDF and b"%PDF-" not in sample[:1024]:
        raise FileUploadError("invalid_pdf", "The file does not contain a valid PDF signature")
    if kind is FileKind.DOCX and not sample.startswith((b"PK\x03\x04", b"PK\x05\x06")):
        raise FileUploadError("invalid_docx", "The file does not contain a valid DOCX archive")
    if kind in {FileKind.TEXT, FileKind.MARKDOWN}:
        if b"\x00" in sample:
            raise FileUploadError("invalid_text", "Text files cannot contain NUL bytes")
        try:
            codecs.getincrementaldecoder("utf-8-sig")().decode(sample, final=False)
        except UnicodeDecodeError as exc:
            raise FileUploadError("invalid_text_encoding", "Text files must use UTF-8") from exc


async def validated_upload_chunks(
    upload: UploadReader,
    *,
    kind: FileKind,
    max_bytes: int,
    chunk_bytes: int,
) -> AsyncIterator[bytes]:
    size_bytes = 0
    first = True
    while chunk := await upload.read(chunk_bytes):
        size_bytes += len(chunk)
        if size_bytes > max_bytes:
            raise FileTooLargeError(
                "file_too_large",
                f"File exceeds the {max_bytes}-byte upload limit",
            )
        if first:
            _validate_signature(kind, chunk)
            first = False
        yield chunk
    if first:
        raise FileUploadError("empty_file", "The uploaded file is empty")


class FileSourceService:
    """Store validated bytes and atomically create durable ingestion state."""

    def __init__(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        storage: ObjectStorage,
        queue: IngestionQueue,
    ) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.storage = storage
        self.queue = queue
        self.bots = BotRepository(session, tenant_id)
        self.sources = KnowledgeSourceRepository(session, tenant_id)
        self.documents = DocumentRepository(session, tenant_id)
        self.jobs = IngestionJobRepository(session, tenant_id)

    async def create(
        self,
        *,
        bot_id: UUID,
        upload: UploadReader,
        display_name: str | None,
    ) -> KnowledgeSource:
        if await self.bots.get(bot_id) is None:
            raise FileUploadError("bot_not_found", "Bot not found")
        filename = sanitize_upload_filename(upload.filename)
        kind = classify_upload(filename, upload.content_type)
        source = await self.sources.create(
            bot_id=bot_id,
            source_type=KnowledgeSourceType.FILE,
            name=(display_name.strip() if display_name and display_name.strip() else filename),
        )
        storage_key = f"sources/{source.id}/raw/input.{kind.value}"
        stored = None
        try:
            stored = await self.storage.put_stream(
                self.tenant_id,
                storage_key,
                validated_upload_chunks(
                    upload,
                    kind=kind,
                    max_bytes=settings.FILE_UPLOAD_MAX_BYTES,
                    chunk_bytes=settings.FILE_UPLOAD_CHUNK_BYTES,
                ),
            )
            source.configuration = {
                "original_filename": filename,
                "file_kind": kind.value,
                "media_type": upload.content_type or "application/octet-stream",
                "size_bytes": stored.size_bytes,
                "checksum_sha256": stored.checksum_sha256,
                "storage_key": stored.key,
            }
            job, _created = await self.jobs.create_or_get(
                source_id=source.id,
                job_type=IngestionJobType.INGEST_SOURCE,
                idempotency_key=f"file:{source.id}:{stored.checksum_sha256}",
                payload={"checksum_sha256": stored.checksum_sha256},
                max_attempts=settings.INGESTION_MAX_ATTEMPTS,
            )
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            if stored is not None:
                await self.storage.delete(self.tenant_id, stored.key)
            raise

        try:
            await self.queue.enqueue(IngestionQueueMessage(self.tenant_id, job.id))
        except Exception:
            logger.warning(
                "ingestion_dispatch_deferred",
                tenant_id=str(self.tenant_id),
                source_id=str(source.id),
                job_id=str(job.id),
            )
        return source

    async def delete(self, source_id: UUID) -> bool:
        source = await self.sources.get(source_id)
        if source is None:
            return False
        source.status = KnowledgeSourceStatus.DELETING
        await self.session.commit()

        keys = {
            key
            for key in [source.configuration.get("storage_key")]
            if isinstance(key, str)
        }
        for document in await self.documents.list_for_source(source.id):
            keys.update(
                key
                for key in [document.raw_storage_key, document.normalized_storage_key]
                if key is not None
            )
        try:
            for key in keys:
                await self.storage.delete(self.tenant_id, key)
        except Exception:
            await self.sources.set_status(
                source.id,
                KnowledgeSourceStatus.FAILED,
                error_code="storage_cleanup_failed",
                error_message="Source storage cleanup failed",
            )
            await self.session.commit()
            raise
        await self.sources.delete(source)
        await self.session.commit()
        return True


__all__ = [
    "FileKind",
    "FileSourceService",
    "FileTooLargeError",
    "FileUploadError",
    "UploadReader",
    "classify_upload",
    "sanitize_upload_filename",
    "validated_upload_chunks",
]
