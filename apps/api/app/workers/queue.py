"""Provider-neutral ingestion queue contract and ARQ adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from arq.connections import ArqRedis, RedisSettings, create_pool

from app.core.config import settings


@dataclass(frozen=True, slots=True)
class IngestionQueueMessage:
    """Minimal tenant-addressed payload; job details remain in PostgreSQL."""

    tenant_id: UUID
    job_id: UUID

    @property
    def queue_job_id(self) -> str:
        return f"ingestion:{self.tenant_id}:{self.job_id}"


class IngestionQueue(Protocol):
    """Queue boundary used by API services and recovery dispatchers."""

    async def enqueue(
        self,
        message: IngestionQueueMessage,
        *,
        defer_until: datetime | None = None,
    ) -> bool: ...


class ArqIngestionQueue:
    """ARQ implementation with a stable queue-level idempotency key."""

    def __init__(self, redis: ArqRedis, queue_name: str | None = None) -> None:
        self.redis = redis
        self.queue_name = settings.INGESTION_QUEUE_NAME if queue_name is None else queue_name

    async def enqueue(
        self,
        message: IngestionQueueMessage,
        *,
        defer_until: datetime | None = None,
    ) -> bool:
        queued = await self.redis.enqueue_job(
            "process_ingestion_job",
            str(message.tenant_id),
            str(message.job_id),
            _job_id=message.queue_job_id,
            _queue_name=self.queue_name,
            _defer_until=defer_until,
        )
        return queued is not None


async def create_ingestion_queue() -> ArqIngestionQueue:
    """Connect the API/recovery process to the configured Redis queue."""

    redis = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
    return ArqIngestionQueue(redis)


__all__ = [
    "ArqIngestionQueue",
    "IngestionQueue",
    "IngestionQueueMessage",
    "create_ingestion_queue",
]
