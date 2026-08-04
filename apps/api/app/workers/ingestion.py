"""ARQ ingestion worker, retry policy, and handler dispatch boundary."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any, ClassVar
from uuid import UUID

import structlog
from arq.connections import RedisSettings
from arq.worker import Retry
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.tenancy import tenant_session_scope
from app.db.base import utc_now
from app.db.session import async_session_factory, dispose_engine
from app.domains.knowledge.enums import IngestionJobState, IngestionJobType, KnowledgeSourceStatus
from app.domains.knowledge.models import IngestionJob
from app.domains.knowledge.repositories import (
    IngestionJobRepository,
    KnowledgeSourceRepository,
)
from app.providers.factory import build_embedding_provider
from app.providers.storage import build_object_storage

logger = structlog.get_logger(__name__)
IngestionHandler = Callable[[AsyncSession, IngestionJob], Awaitable[None]]


class IngestionProcessingError(RuntimeError):
    """Safe, classified failure that may be persisted and shown to a tenant."""

    def __init__(self, code: str, public_message: str) -> None:
        super().__init__(public_message)
        self.code = code
        self.public_message = public_message


class RetryableIngestionError(IngestionProcessingError):
    """A transient failure eligible for bounded retry."""


class PermanentIngestionError(IngestionProcessingError):
    """A deterministic failure that should not be retried."""


class IngestionDispatcher:
    """Maps provider-neutral job types to handlers registered by later tasks."""

    def __init__(self) -> None:
        self._handlers: dict[IngestionJobType, IngestionHandler] = {}

    def register(self, job_type: IngestionJobType, handler: IngestionHandler) -> None:
        self._handlers[job_type] = handler

    async def dispatch(self, session: AsyncSession, job: IngestionJob) -> None:
        handler = self._handlers.get(job.type)
        if handler is None:
            raise PermanentIngestionError(
                "handler_not_configured",
                f"No ingestion handler is configured for {job.type.value}",
            )
        await handler(session, job)


def retry_delay_seconds(attempt: int) -> int:
    """Return deterministic capped exponential backoff for an attempt number."""

    exponent = max(attempt - 1, 0)
    return min(
        settings.INGESTION_RETRY_BASE_SECONDS * (2**exponent),
        settings.INGESTION_RETRY_MAX_SECONDS,
    )


async def _record_retry_or_failure(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    job: IngestionJob,
    code: str,
    public_message: str,
) -> bool:
    delay = retry_delay_seconds(job.attempts)
    scheduled_at = utc_now() + timedelta(seconds=delay)
    jobs = IngestionJobRepository(session, tenant_id)
    sources = KnowledgeSourceRepository(session, tenant_id)
    updated = await jobs.mark_retry(
        job.id,
        error_code=code,
        error_message=public_message,
        scheduled_at=scheduled_at,
    )
    if updated is None:
        await session.rollback()
        return False
    if updated.state is IngestionJobState.RETRY_SCHEDULED:
        await sources.set_status(
            job.source_id,
            KnowledgeSourceStatus.PENDING,
            error_code=code,
            error_message=public_message,
        )
        await session.commit()
        return True
    await sources.set_status(
        job.source_id,
        KnowledgeSourceStatus.FAILED,
        error_code=code,
        error_message=public_message,
    )
    await session.commit()
    return False


async def process_ingestion_job(ctx: dict[str, Any], tenant_id: str, job_id: str) -> None:
    """Claim and run one tenant job without doing work in an API process."""

    parsed_tenant_id = UUID(tenant_id)
    parsed_job_id = UUID(job_id)
    session_factory = ctx.get("session_factory", async_session_factory)
    dispatcher = ctx.get("ingestion_dispatcher")
    if not isinstance(session_factory, async_sessionmaker):
        raise TypeError("Worker session_factory must be an async_sessionmaker")
    if not isinstance(dispatcher, IngestionDispatcher):
        raise TypeError("Worker ingestion_dispatcher must be an IngestionDispatcher")

    async with session_factory() as session, tenant_session_scope(session, parsed_tenant_id):
        jobs = IngestionJobRepository(session)
        sources = KnowledgeSourceRepository(session)
        job = await jobs.claim(parsed_job_id)
        if job is None:
            await session.commit()
            return
        await sources.set_status(job.source_id, KnowledgeSourceStatus.PROCESSING)
        await session.commit()

        try:
            await dispatcher.dispatch(session, job)
        except PermanentIngestionError as exc:
            await session.rollback()
            await jobs.mark_failed(
                job.id,
                error_code=exc.code,
                error_message=exc.public_message,
            )
            await sources.set_status(
                job.source_id,
                KnowledgeSourceStatus.FAILED,
                error_code=exc.code,
                error_message=exc.public_message,
            )
            await session.commit()
        except RetryableIngestionError as exc:
            await session.rollback()
            should_retry = await _record_retry_or_failure(
                session,
                tenant_id=parsed_tenant_id,
                job=job,
                code=exc.code,
                public_message=exc.public_message,
            )
            if should_retry:
                raise Retry(defer=retry_delay_seconds(job.attempts)) from None
        except Exception:
            logger.exception(
                "ingestion_job_unexpected_error",
                tenant_id=str(parsed_tenant_id),
                job_id=str(parsed_job_id),
            )
            await session.rollback()
            should_retry = await _record_retry_or_failure(
                session,
                tenant_id=parsed_tenant_id,
                job=job,
                code="unexpected_error",
                public_message="Ingestion failed unexpectedly",
            )
            if should_retry:
                raise Retry(defer=retry_delay_seconds(job.attempts)) from None
        else:
            await jobs.mark_succeeded(job.id)
            await sources.set_status(job.source_id, KnowledgeSourceStatus.READY)
            await session.commit()


async def startup(ctx: dict[str, Any]) -> None:
    """Create the registry that source-specific tasks extend."""

    from app.workers.source_ingestion import SourceIngestionHandler

    dispatcher = IngestionDispatcher()
    embedding_provider = build_embedding_provider()
    dispatcher.register(
        IngestionJobType.INGEST_SOURCE,
        SourceIngestionHandler(build_object_storage(), embedding_provider),
    )
    ctx["session_factory"] = async_session_factory
    ctx["ingestion_dispatcher"] = dispatcher
    ctx["embedding_provider"] = embedding_provider


async def shutdown(ctx: dict[str, Any]) -> None:
    provider = ctx.get("embedding_provider")
    close = getattr(provider, "aclose", None)
    if close is not None:
        await close()
    await dispose_engine()


class WorkerSettings:
    functions: ClassVar[list[Any]] = [process_ingestion_job]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    queue_name = settings.INGESTION_QUEUE_NAME
    job_timeout = settings.INGESTION_JOB_TIMEOUT_SECONDS
    max_tries = settings.INGESTION_MAX_ATTEMPTS
    retry_jobs = True


__all__ = [
    "IngestionDispatcher",
    "IngestionProcessingError",
    "PermanentIngestionError",
    "RetryableIngestionError",
    "WorkerSettings",
    "process_ingestion_job",
    "retry_delay_seconds",
]
