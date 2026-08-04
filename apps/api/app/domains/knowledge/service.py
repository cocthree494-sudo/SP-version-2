"""Knowledge source creation and durable-to-Redis job dispatch."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domains.bots.repositories import BotRepository
from app.domains.knowledge.enums import IngestionJobType, KnowledgeSourceType
from app.domains.knowledge.models import IngestionJob, KnowledgeSource
from app.domains.knowledge.repositories import (
    IngestionJobRepository,
    KnowledgeSourceRepository,
)
from app.workers.queue import IngestionQueue, IngestionQueueMessage


class KnowledgeDomainError(RuntimeError):
    """Base class for expected knowledge-domain failures."""


class KnowledgeBotNotFoundError(KnowledgeDomainError):
    """Raised when a bot is absent from the active tenant."""


class KnowledgeSourceNotFoundError(KnowledgeDomainError):
    """Raised when a source is absent from the active tenant."""


class IngestionService:
    """Create tenant sources and idempotently dispatch background work."""

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

    async def create_source(
        self,
        *,
        bot_id: UUID,
        source_type: KnowledgeSourceType,
        name: str,
        configuration: dict[str, Any] | None = None,
    ) -> KnowledgeSource:
        if await self.bots.get(bot_id) is None:
            raise KnowledgeBotNotFoundError("Bot not found")
        source = await self.sources.create(
            bot_id=bot_id,
            source_type=source_type,
            name=name,
            configuration=configuration,
        )
        await self.session.commit()
        return source

    async def enqueue_source(
        self,
        *,
        source_id: UUID,
        idempotency_key: str,
        job_type: IngestionJobType = IngestionJobType.INGEST_SOURCE,
        payload: dict[str, Any] | None = None,
        max_attempts: int | None = None,
    ) -> IngestionJob:
        if await self.sources.get(source_id) is None:
            raise KnowledgeSourceNotFoundError("Knowledge source not found")
        job, _created = await self.jobs.create_or_get(
            source_id=source_id,
            job_type=job_type,
            idempotency_key=idempotency_key,
            payload=payload,
            max_attempts=(
                settings.INGESTION_MAX_ATTEMPTS if max_attempts is None else max_attempts
            ),
        )
        # Commit the durable job before the Redis dispatch. Repeating this call
        # is safe: both PostgreSQL and ARQ use stable idempotency identifiers.
        await self.session.commit()
        await self.queue.enqueue(IngestionQueueMessage(self.tenant_id, job.id))
        return job

    async def redispatch_pending(self, *, limit: int = 100) -> int:
        """Recover jobs committed during a transient Redis outage."""

        dispatched = 0
        for job in await self.jobs.list_dispatchable(limit=limit):
            if await self.queue.enqueue(
                IngestionQueueMessage(self.tenant_id, job.id),
                defer_until=job.scheduled_at,
            ):
                dispatched += 1
        return dispatched


__all__ = [
    "IngestionService",
    "KnowledgeBotNotFoundError",
    "KnowledgeDomainError",
    "KnowledgeSourceNotFoundError",
]
