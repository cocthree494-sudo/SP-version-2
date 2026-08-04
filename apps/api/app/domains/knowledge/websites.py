"""Website source creation and idempotent crawl dispatch."""

from __future__ import annotations

import hashlib
import json
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domains.bots.repositories import BotRepository
from app.domains.knowledge.enums import IngestionJobType, KnowledgeSourceType
from app.domains.knowledge.models import KnowledgeSource
from app.domains.knowledge.repositories import IngestionJobRepository, KnowledgeSourceRepository
from app.domains.knowledge.schemas import WebsiteSourceCreateRequest
from app.workers.queue import IngestionQueue, IngestionQueueMessage

logger = structlog.get_logger(__name__)


class WebsiteSourceError(ValueError):
    pass


class WebsiteSourceService:
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
        payload: WebsiteSourceCreateRequest,
    ) -> KnowledgeSource:
        if await self.bots.get(bot_id) is None:
            raise WebsiteSourceError("Bot not found")
        configuration = {
            "start_url": payload.url,
            "max_pages": payload.max_pages,
            "max_depth": payload.max_depth,
            "request_delay_seconds": payload.request_delay_seconds,
        }
        source = await self.sources.create(
            bot_id=bot_id,
            source_type=KnowledgeSourceType.WEBSITE,
            name=payload.name or payload.url,
            configuration=configuration,
        )
        fingerprint = hashlib.sha256(
            json.dumps(configuration, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        job, _created = await self.jobs.create_or_get(
            source_id=source.id,
            job_type=IngestionJobType.INGEST_SOURCE,
            idempotency_key=f"website:{source.id}:{fingerprint}",
            payload={"configuration_sha256": fingerprint},
            max_attempts=settings.INGESTION_MAX_ATTEMPTS,
        )
        await self.session.commit()
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


__all__ = ["WebsiteSourceError", "WebsiteSourceService"]
