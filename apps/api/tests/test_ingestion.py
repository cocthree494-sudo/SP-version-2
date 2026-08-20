"""Knowledge schema, idempotent dispatch, retry, and tenant isolation tests."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import AsyncGenerator
from datetime import datetime
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
import pytest_asyncio
from arq.connections import ArqRedis
from arq.worker import Retry
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.domains.bots.enums import BotStatus
from app.domains.bots.models import Bot
from app.domains.bots.repositories import BotRepository
from app.domains.knowledge.embedding_pipeline import EmbeddingPipeline, EmbeddingPipelineError
from app.domains.knowledge.enums import (
    DocumentStatus,
    IngestionJobState,
    IngestionJobType,
    KnowledgeSourceStatus,
    KnowledgeSourceType,
)
from app.domains.knowledge.models import Document, DocumentChunk, IngestionJob, KnowledgeSource
from app.domains.knowledge.repositories import (
    DocumentChunkRepository,
    DocumentRepository,
    IdempotencyConflictError,
    IngestionJobRepository,
    KnowledgeSourceRepository,
)
from app.domains.knowledge.service import IngestionService
from app.domains.tenancy.models import Tenant
from app.domains.tenancy.repositories import TenantRepository
from app.providers.embeddings import (
    DeterministicEmbeddingProvider,
    EmbeddingProviderError,
)
from app.providers.types import ProviderErrorCategory
from app.workers.ingestion import (
    IngestionDispatcher,
    RetryableIngestionError,
    process_ingestion_job,
)
from app.workers.queue import ArqIngestionQueue, IngestionQueueMessage


def test_standalone_worker_registers_all_model_mappings() -> None:
    api_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from sqlalchemy.orm import configure_mappers; "
                "import app.workers.ingestion; "
                "configure_mappers()"
            ),
        ],
        cwd=api_root,
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
            "REDIS_URL": "redis://127.0.0.1:6379/0",
        },
    )
    assert completed.returncode == 0, completed.stderr


class FakeQueue:
    def __init__(self) -> None:
        self.messages: list[IngestionQueueMessage] = []

    async def enqueue(
        self,
        message: IngestionQueueMessage,
        *,
        defer_until: datetime | None = None,
    ) -> bool:
        del defer_until
        if message in self.messages:
            return False
        self.messages.append(message)
        return True


class FakeArqRedis:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[str, str], dict[str, object]]] = []

    async def enqueue_job(
        self,
        function: str,
        *args: str,
        **kwargs: object,
    ) -> object:
        self.calls.append((function, cast(tuple[str, str], args), kwargs))
        return object()


@pytest_asyncio.fixture
async def ingestion_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    engine: AsyncEngine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )
    tables = [
        cast(Table, Tenant.__table__),
        cast(Table, Bot.__table__),
        cast(Table, KnowledgeSource.__table__),
        cast(Table, Document.__table__),
        cast(Table, DocumentChunk.__table__),
        cast(Table, IngestionJob.__table__),
    ]
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=tables)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def create_tenant_bot(
    session: AsyncSession,
    *,
    slug: str,
) -> tuple[UUID, UUID]:
    tenant = await TenantRepository(session).create(name=slug.title(), slug=slug)
    bot = await BotRepository(session, tenant.id).create(
        name=f"{slug.title()} Bot",
        system_policy=None,
        default_language="auto",
        status=BotStatus.ACTIVE,
        widget_welcome_text="How can we help?",
        widget_accent_color="#194f46",
        widget_position="right",
    )
    await session.commit()
    return tenant.id, bot.id


@pytest.mark.asyncio
async def test_source_documents_and_jobs_are_tenant_scoped_and_idempotent(
    ingestion_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with ingestion_factory() as session:
        tenant_a, bot_a = await create_tenant_bot(session, slug="alpha")
        tenant_b, bot_b = await create_tenant_bot(session, slug="beta")
        source_a = await KnowledgeSourceRepository(session, tenant_a).create(
            bot_id=bot_a,
            source_type=KnowledgeSourceType.FILE,
            name="Guide",
        )
        source_b = await KnowledgeSourceRepository(session, tenant_b).create(
            bot_id=bot_b,
            source_type=KnowledgeSourceType.FILE,
            name="Private Guide",
        )
        document_v1 = await DocumentRepository(session, tenant_a).create_next_version(
            source_id=source_a.id,
            checksum_sha256="a" * 64,
        )
        document_v2 = await DocumentRepository(session, tenant_a).create_next_version(
            source_id=source_a.id,
            checksum_sha256="b" * 64,
        )
        await DocumentRepository(session, tenant_a).activate(document_v1)
        await DocumentRepository(session, tenant_a).activate(document_v2)
        jobs_a = IngestionJobRepository(session, tenant_a)
        job, created = await jobs_a.create_or_get(
            source_id=source_a.id,
            job_type=IngestionJobType.INGEST_SOURCE,
            idempotency_key="file:checksum-a",
            payload={"storage_key": "sources/a/input.pdf"},
            max_attempts=5,
        )
        same_job, created_again = await jobs_a.create_or_get(
            source_id=source_a.id,
            job_type=IngestionJobType.INGEST_SOURCE,
            idempotency_key="file:checksum-a",
            payload={"storage_key": "sources/a/input.pdf"},
            max_attempts=5,
        )
        await session.commit()

        assert document_v1.status is DocumentStatus.SUPERSEDED
        assert document_v2.status is DocumentStatus.ACTIVE
        assert document_v2.version == 2
        assert created is True
        assert created_again is False
        assert same_job.id == job.id
        assert await KnowledgeSourceRepository(session, tenant_a).get(source_b.id) is None
        assert await IngestionJobRepository(session, tenant_b).get(job.id) is None

        with pytest.raises(IdempotencyConflictError):
            await jobs_a.create_or_get(
                source_id=source_a.id,
                job_type=IngestionJobType.DELETE_SOURCE,
                idempotency_key="file:checksum-a",
                payload={"storage_key": "sources/a/input.pdf"},
                max_attempts=5,
            )


@pytest.mark.asyncio
async def test_service_commits_durable_job_then_dispatches_stable_message(
    ingestion_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with ingestion_factory() as session:
        tenant_id, bot_id = await create_tenant_bot(session, slug="dispatch")
        queue = FakeQueue()
        service = IngestionService(session, tenant_id, queue)
        source = await service.create_source(
            bot_id=bot_id,
            source_type=KnowledgeSourceType.FILE,
            name="Product manual",
        )
        first = await service.enqueue_source(
            source_id=source.id,
            idempotency_key="upload:sha256",
            payload={"storage_key": "sources/manual.pdf"},
        )
        second = await service.enqueue_source(
            source_id=source.id,
            idempotency_key="upload:sha256",
            payload={"storage_key": "sources/manual.pdf"},
        )

        assert first.id == second.id
        assert queue.messages == [IngestionQueueMessage(tenant_id, first.id)]
        assert (await IngestionJobRepository(session, tenant_id).get(first.id)) is not None


@pytest.mark.asyncio
async def test_worker_marks_success_and_schedules_bounded_retry(
    ingestion_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with ingestion_factory() as session:
        tenant_id, bot_id = await create_tenant_bot(session, slug="worker")
        source = await KnowledgeSourceRepository(session, tenant_id).create(
            bot_id=bot_id,
            source_type=KnowledgeSourceType.FILE,
            name="Worker input",
        )
        success_job, _ = await IngestionJobRepository(session, tenant_id).create_or_get(
            source_id=source.id,
            job_type=IngestionJobType.INGEST_SOURCE,
            idempotency_key="worker:success",
            max_attempts=3,
        )
        retry_job, _ = await IngestionJobRepository(session, tenant_id).create_or_get(
            source_id=source.id,
            job_type=IngestionJobType.DELETE_SOURCE,
            idempotency_key="worker:retry",
            max_attempts=3,
        )
        await session.commit()

    dispatcher = IngestionDispatcher()

    async def succeed(_session: AsyncSession, _job: IngestionJob) -> None:
        return None

    async def retry(_session: AsyncSession, _job: IngestionJob) -> None:
        _job.progress_percent = 12
        await _session.flush()
        raise RetryableIngestionError("storage_unavailable", "Storage is temporarily unavailable")

    dispatcher.register(IngestionJobType.INGEST_SOURCE, succeed)
    dispatcher.register(IngestionJobType.DELETE_SOURCE, retry)
    ctx = {"session_factory": ingestion_factory, "ingestion_dispatcher": dispatcher}

    await process_ingestion_job(ctx, str(tenant_id), str(success_job.id))
    with pytest.raises(Retry):
        await process_ingestion_job(ctx, str(tenant_id), str(retry_job.id))

    async with ingestion_factory() as session:
        persisted_success = await IngestionJobRepository(session, tenant_id).get(success_job.id)
        persisted_retry = await IngestionJobRepository(session, tenant_id).get(retry_job.id)
        persisted_source = await KnowledgeSourceRepository(session, tenant_id).get(source.id)
        assert persisted_success is not None
        assert persisted_success.state is IngestionJobState.SUCCEEDED
        assert persisted_success.progress_percent == 100
        assert persisted_retry is not None
        assert persisted_retry.state is IngestionJobState.RETRY_SCHEDULED
        assert persisted_retry.attempts == 1
        assert persisted_retry.scheduled_at is not None
        assert persisted_retry.error_code == "storage_unavailable"
        assert persisted_source is not None
        assert persisted_source.status is KnowledgeSourceStatus.PENDING


@pytest.mark.asyncio
async def test_arq_adapter_uses_tenant_job_id_as_queue_id() -> None:
    redis = FakeArqRedis()
    queue = ArqIngestionQueue(cast(ArqRedis, redis), queue_name="test-ingestion")
    message = IngestionQueueMessage(UUID(int=1), UUID(int=2))

    assert await queue.enqueue(message) is True
    function, args, kwargs = redis.calls[0]
    assert function == "process_ingestion_job"
    assert args == (str(message.tenant_id), str(message.job_id))
    assert kwargs["_job_id"] == message.queue_job_id
    assert kwargs["_queue_name"] == "test-ingestion"
    assert kwargs["_defer_until"] is None


@pytest.mark.asyncio
async def test_embedding_pipeline_batches_chunks_and_classifies_retry(
    ingestion_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with ingestion_factory() as session:
        tenant_id, bot_id = await create_tenant_bot(session, slug="embedding")
        source = await KnowledgeSourceRepository(session, tenant_id).create(
            bot_id=bot_id,
            source_type=KnowledgeSourceType.MANUAL,
            name="Embedding fixture",
        )
        document = await DocumentRepository(session, tenant_id).create_next_version(
            source_id=source.id,
            checksum_sha256="c" * 64,
        )
        result = await EmbeddingPipeline(
            session,
            tenant_id,
            DeterministicEmbeddingProvider(dimensions=16),
        ).run(document, "# Policy\n\n" + " ".join(f"token-{index}" for index in range(900)))
        chunks = await DocumentChunkRepository(session, tenant_id).list_for_document(document.id)
        assert result.chunk_count == len(chunks)
        assert result.chunk_count > 1
        assert all(len(chunk.embedding) == 16 for chunk in chunks)

        retry_document = await DocumentRepository(session, tenant_id).create_next_version(
            source_id=source.id,
            checksum_sha256="d" * 64,
        )

        class UnavailableProvider:
            provider_id = "unavailable"
            model_id = "configured"
            dimensions = 16

            async def embed(self, _texts):  # type: ignore[no-untyped-def]
                raise EmbeddingProviderError(
                    ProviderErrorCategory.UNAVAILABLE,
                    "Embedding provider is temporarily unavailable",
                    provider_id=self.provider_id,
                )

        with pytest.raises(EmbeddingPipelineError) as captured:
            await EmbeddingPipeline(
                session,
                tenant_id,
                UnavailableProvider(),
            ).run(retry_document, "Retry this content")
        assert captured.value.retryable is True
