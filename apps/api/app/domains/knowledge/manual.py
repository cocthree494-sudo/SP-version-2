"""Authoritative manual Q&A creation, editing, and re-ingestion."""

from __future__ import annotations

import hashlib
from uuid import UUID, uuid4

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
from app.domains.knowledge.repositories import IngestionJobRepository, KnowledgeSourceRepository
from app.domains.knowledge.schemas import ManualSourceCreateRequest, ManualSourceUpdateRequest
from app.workers.queue import IngestionQueue, IngestionQueueMessage

logger = structlog.get_logger(__name__)


class ManualSourceError(ValueError):
    pass


def manual_document_text(question: str, answer: str) -> str:
    return f"# {question.strip()}\n\n{answer.strip()}"


def manual_checksum(question: str, answer: str) -> str:
    return hashlib.sha256(manual_document_text(question, answer).encode("utf-8")).hexdigest()


class ManualSourceService:
    def __init__(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        queue: IngestionQueue,
    ) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.queue = queue
        self.bots = BotRepository(session, tenant_id)
        self.sources = KnowledgeSourceRepository(session, tenant_id)
        self.jobs = IngestionJobRepository(session, tenant_id)

    async def create(
        self,
        *,
        bot_id: UUID,
        payload: ManualSourceCreateRequest,
    ) -> KnowledgeSource:
        if await self.bots.get(bot_id) is None:
            raise ManualSourceError("Bot not found")
        checksum = manual_checksum(payload.question, payload.answer)
        source = await self.sources.create(
            bot_id=bot_id,
            source_type=KnowledgeSourceType.MANUAL,
            name=payload.name or payload.question[:200],
            configuration={
                "question": payload.question,
                "answer": payload.answer,
                "checksum_sha256": checksum,
            },
        )
        job = await self._create_job(source, checksum, suffix="create")
        await self.session.commit()
        await self._dispatch(source, job)
        return source

    async def update(
        self,
        *,
        source_id: UUID,
        payload: ManualSourceUpdateRequest,
    ) -> KnowledgeSource:
        source = await self.sources.get(source_id)
        if source is None or source.type is not KnowledgeSourceType.MANUAL:
            raise ManualSourceError("Manual source not found")
        old_question = str(source.configuration["question"])
        old_answer = str(source.configuration["answer"])
        question = payload.question if payload.question is not None else old_question
        answer = payload.answer if payload.answer is not None else old_answer
        if payload.name is not None:
            source.name = payload.name
        changed = question != old_question or answer != old_answer
        if not changed:
            await self.session.commit()
            return source
        checksum = manual_checksum(question, answer)
        source.configuration = {
            "question": question,
            "answer": answer,
            "checksum_sha256": checksum,
        }
        source.status = KnowledgeSourceStatus.PENDING
        source.error_code = None
        source.error_message = None
        job = await self._create_job(source, checksum, suffix=uuid4().hex)
        await self.session.commit()
        await self._dispatch(source, job)
        return source

    async def _create_job(
        self,
        source: KnowledgeSource,
        checksum: str,
        *,
        suffix: str,
    ):
        job, _created = await self.jobs.create_or_get(
            source_id=source.id,
            job_type=IngestionJobType.INGEST_SOURCE,
            idempotency_key=f"manual:{source.id}:{checksum}:{suffix}",
            payload={"checksum_sha256": checksum},
            max_attempts=settings.INGESTION_MAX_ATTEMPTS,
        )
        return job

    async def _dispatch(self, source: KnowledgeSource, job) -> None:  # type: ignore[no-untyped-def]
        try:
            await self.queue.enqueue(IngestionQueueMessage(self.tenant_id, job.id))
        except Exception:
            logger.warning(
                "ingestion_dispatch_deferred",
                tenant_id=str(self.tenant_id),
                source_id=str(source.id),
                job_id=str(job.id),
            )


__all__ = ["ManualSourceError", "ManualSourceService", "manual_checksum", "manual_document_text"]
