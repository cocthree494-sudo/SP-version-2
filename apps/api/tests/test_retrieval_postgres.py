"""Exercise the live pgvector/GIN retrieval branch and its tenant boundary."""

from __future__ import annotations

import hashlib
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.tenancy import set_database_tenant
from app.domains.bots.enums import BotStatus
from app.domains.bots.repositories import BotRepository
from app.domains.knowledge.enums import KnowledgeSourceStatus, KnowledgeSourceType
from app.domains.knowledge.repositories import (
    DocumentChunkRepository,
    DocumentRepository,
    KnowledgeSourceRepository,
)
from app.domains.knowledge.retrieval import HybridRetrievalService
from app.domains.tenancy.repositories import TenantRepository
from app.providers.embeddings import DeterministicEmbeddingProvider, estimate_tokens


async def _add_knowledge(
    session: AsyncSession,
    provider: DeterministicEmbeddingProvider,
    *,
    slug: str,
    contents: list[str],
) -> tuple[UUID, UUID, UUID]:
    tenant = await TenantRepository(session).create(name=slug, slug=slug)
    await set_database_tenant(session, tenant.id)
    bot = await BotRepository(session, tenant.id).create(
        name="PostgreSQL retrieval bot",
        system_policy=None,
        default_language="auto",
        status=BotStatus.ACTIVE,
        widget_welcome_text="How can we help?",
        widget_accent_color="#194f46",
        widget_position="right",
    )
    source = await KnowledgeSourceRepository(session, tenant.id).create(
        bot_id=bot.id,
        source_type=KnowledgeSourceType.MANUAL,
        name="PostgreSQL retrieval source",
    )
    source.status = KnowledgeSourceStatus.READY
    checksum = hashlib.sha256("\n".join(contents).encode()).hexdigest()
    document = await DocumentRepository(session, tenant.id).create_next_version(
        source_id=source.id,
        checksum_sha256=checksum,
        title="PostgreSQL retrieval document",
        canonical_url=f"https://{slug}.example/source",
    )
    embeddings = await provider.embed(contents)
    await DocumentChunkRepository(session, tenant.id).create_batch(
        document=document,
        chunks=[
            {
                "ordinal": ordinal,
                "content": content,
                "content_checksum_sha256": hashlib.sha256(content.encode()).hexdigest(),
                "token_count": estimate_tokens(content),
                "start_char": 0,
                "end_char": len(content),
                "embedding": embedding,
                "embedding_provider": provider.provider_id,
                "embedding_model": provider.model_id,
                "chunk_metadata": {"language": "en"},
            }
            for ordinal, (content, embedding) in enumerate(
                zip(contents, embeddings.embeddings, strict=True)
            )
        ],
    )
    await DocumentRepository(session, tenant.id).activate(document)
    return tenant.id, bot.id, source.id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pgvector_retrieval_orders_results_and_never_leaks_tenant_data(
    pg_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = DeterministicEmbeddingProvider(dimensions=16)
    tenant_a, bot_a, source_a = await _add_knowledge(
        pg_session,
        provider,
        slug="postgres-retrieval-a",
        contents=[
            "Refunds are available within thirty days for unopened items.",
            "Shipping takes two business days after dispatch.",
        ],
    )
    _tenant_b, _bot_b, _source_b = await _add_knowledge(
        pg_session,
        provider,
        slug="postgres-retrieval-b",
        contents=["Private tenant B secret refund code is BETA-ONLY."],
    )

    async def portable_branch_must_not_run(
        *args: object,
        **kwargs: object,
    ) -> tuple[list[object], ...]:
        del args, kwargs
        raise AssertionError("PostgreSQL retrieval unexpectedly used the portable branch")

    monkeypatch.setattr(
        HybridRetrievalService,
        "_portable_candidates",
        portable_branch_must_not_run,
    )
    service = HybridRetrievalService(pg_session, tenant_a, provider)
    assert pg_session.get_bind().dialect.name == "postgresql"
    results = await service.retrieve(
        bot_id=bot_a,
        query="Refunds are available within thirty days for unopened items.",
        language="en",
        top_k=2,
    )

    assert len(results) == 2
    assert results[0].content.startswith("Refunds are available")
    assert results[0].score > results[1].score
    assert results[0].vector_score is not None
    assert all(result.citation.source_id == source_a for result in results)
    assert all("BETA-ONLY" not in result.content for result in results)

    conversational_results = await service.retrieve(
        bot_id=bot_a,
        query="How many days do I have to request a refund?",
        language="en",
        top_k=2,
    )

    assert conversational_results[0].content.startswith("Refunds are available")
    assert conversational_results[0].lexical_score is not None
    assert conversational_results[0].score >= settings.CHAT_MIN_GROUNDED_SCORE
