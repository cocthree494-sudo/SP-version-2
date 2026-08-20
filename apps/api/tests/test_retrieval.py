"""Hybrid retrieval quality fixtures and cross-tenant negative paths."""

from __future__ import annotations

import hashlib
from collections.abc import AsyncGenerator
from typing import cast
from uuid import UUID

import pytest
import pytest_asyncio
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
from app.domains.knowledge.enums import KnowledgeSourceStatus, KnowledgeSourceType
from app.domains.knowledge.models import Document, DocumentChunk, KnowledgeSource
from app.domains.knowledge.repositories import (
    DocumentChunkRepository,
    DocumentRepository,
    KnowledgeSourceRepository,
)
from app.domains.knowledge.retrieval import HybridRetrievalService
from app.domains.tenancy.models import Tenant
from app.domains.tenancy.repositories import TenantRepository
from app.providers.embeddings import DeterministicEmbeddingProvider, estimate_tokens


@pytest_asyncio.fixture
async def retrieval_session() -> AsyncGenerator[AsyncSession, None]:
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
    ]
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=tables)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def add_knowledge(
    session: AsyncSession,
    provider: DeterministicEmbeddingProvider,
    *,
    tenant_slug: str,
    content: str,
) -> tuple[UUID, UUID, UUID]:
    tenant = await TenantRepository(session).create(name=tenant_slug.title(), slug=tenant_slug)
    bot = await BotRepository(session, tenant.id).create(
        name="Support",
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
        name="Refunds",
    )
    source.status = KnowledgeSourceStatus.READY
    checksum = hashlib.sha256(content.encode()).hexdigest()
    document = await DocumentRepository(session, tenant.id).create_next_version(
        source_id=source.id,
        checksum_sha256=checksum,
        title="Refund policy",
        canonical_url=f"https://{tenant_slug}.example/refunds",
    )
    embedded = await provider.embed([content])
    await DocumentChunkRepository(session, tenant.id).create_batch(
        document=document,
        chunks=[
            {
                "ordinal": 0,
                "content": content,
                "content_checksum_sha256": checksum,
                "token_count": estimate_tokens(content),
                "start_char": 0,
                "end_char": len(content),
                "embedding": embedded.embeddings[0],
                "embedding_provider": provider.provider_id,
                "embedding_model": provider.model_id,
                "chunk_metadata": {"language": "en"},
            }
        ],
    )
    await DocumentRepository(session, tenant.id).activate(document)
    await session.commit()
    return tenant.id, bot.id, source.id


@pytest.mark.asyncio
async def test_hybrid_retrieval_returns_citations_and_never_crosses_tenants(
    retrieval_session: AsyncSession,
) -> None:
    provider = DeterministicEmbeddingProvider(dimensions=16)
    tenant_a, bot_a, source_a = await add_knowledge(
        retrieval_session,
        provider,
        tenant_slug="retrieval-a",
        content="Customers may request a refund within thirty days.",
    )
    _tenant_b, _bot_b, _source_b = await add_knowledge(
        retrieval_session,
        provider,
        tenant_slug="retrieval-b",
        content="Private tenant secret refund code is BETA-ONLY.",
    )

    results = await HybridRetrievalService(
        retrieval_session,
        tenant_a,
        provider,
    ).retrieve(
        bot_id=bot_a,
        query="What is the refund policy?",
        source_ids={source_a},
        language="en",
    )

    assert len(results) == 1
    assert "thirty days" in results[0].content
    assert "BETA-ONLY" not in results[0].content
    assert results[0].citation.source_id == source_a
    assert results[0].citation.title == "Refund policy"
    assert results[0].score > 0


@pytest.mark.asyncio
async def test_retrieval_filters_unknown_source_and_blank_query(
    retrieval_session: AsyncSession,
) -> None:
    provider = DeterministicEmbeddingProvider(dimensions=16)
    tenant_id, bot_id, _source_id = await add_knowledge(
        retrieval_session,
        provider,
        tenant_slug="retrieval-filter",
        content="Shipping takes two days.",
    )
    service = HybridRetrievalService(retrieval_session, tenant_id, provider)
    assert await service.retrieve(bot_id=bot_id, query="   ") == []
    assert await service.retrieve(
        bot_id=bot_id,
        query="shipping",
        source_ids={UUID(int=999)},
    ) == []


@pytest.mark.asyncio
async def test_lexical_source_match_excludes_unrelated_semantic_source(
    retrieval_session: AsyncSession,
) -> None:
    provider = DeterministicEmbeddingProvider(dimensions=16)
    tenant = await TenantRepository(retrieval_session).create(
        name="Mixed sources",
        slug="mixed-sources",
    )
    bot = await BotRepository(retrieval_session, tenant.id).create(
        name="Support",
        system_policy=None,
        default_language="auto",
        status=BotStatus.ACTIVE,
        widget_welcome_text="How can we help?",
        widget_accent_color="#194f46",
        widget_position="right",
    )
    website = await KnowledgeSourceRepository(retrieval_session, tenant.id).create(
        bot_id=bot.id,
        source_type=KnowledgeSourceType.WEBSITE,
        name="Website",
    )
    website.status = KnowledgeSourceStatus.READY
    website_text = "NPC Automators builds custom automation and AI integrations."
    website_doc = await DocumentRepository(retrieval_session, tenant.id).create_next_version(
        source_id=website.id,
        checksum_sha256=hashlib.sha256(website_text.encode()).hexdigest(),
        title="NPC Automators",
        canonical_url="https://www.npcautomators.com/",
    )
    website_embedding = await provider.embed([website_text])
    await DocumentChunkRepository(retrieval_session, tenant.id).create_batch(
        document=website_doc,
        chunks=[
            {
                "ordinal": 0,
                "content": website_text,
                "content_checksum_sha256": hashlib.sha256(website_text.encode()).hexdigest(),
                "token_count": estimate_tokens(website_text),
                "start_char": 0,
                "end_char": len(website_text),
                "embedding": website_embedding.embeddings[0],
                "embedding_provider": provider.provider_id,
                "embedding_model": provider.model_id,
                "chunk_metadata": {},
            }
        ],
    )
    await DocumentRepository(retrieval_session, tenant.id).activate(website_doc)

    unrelated = await KnowledgeSourceRepository(retrieval_session, tenant.id).create(
        bot_id=bot.id,
        source_type=KnowledgeSourceType.FILE,
        name="Unrelated file",
    )
    unrelated.status = KnowledgeSourceStatus.READY
    unrelated_text = "Our support work handles desk orders and shipping returns."
    unrelated_doc = await DocumentRepository(retrieval_session, tenant.id).create_next_version(
        source_id=unrelated.id,
        checksum_sha256=hashlib.sha256(unrelated_text.encode()).hexdigest(),
        title="Unrelated file",
    )
    unrelated_embedding = await provider.embed([unrelated_text])
    await DocumentChunkRepository(retrieval_session, tenant.id).create_batch(
        document=unrelated_doc,
        chunks=[
            {
                "ordinal": 0,
                "content": unrelated_text,
                "content_checksum_sha256": hashlib.sha256(unrelated_text.encode()).hexdigest(),
                "token_count": estimate_tokens(unrelated_text),
                "start_char": 0,
                "end_char": len(unrelated_text),
                "embedding": unrelated_embedding.embeddings[0],
                "embedding_provider": provider.provider_id,
                "embedding_model": provider.model_id,
                "chunk_metadata": {},
            }
        ],
    )
    await DocumentRepository(retrieval_session, tenant.id).activate(unrelated_doc)
    await retrieval_session.commit()

    results = await HybridRetrievalService(
        retrieval_session,
        tenant.id,
        provider,
    ).retrieve(bot_id=bot.id, query="What does NPC Automators do?")

    assert results
    assert all(item.citation.source_id == website.id for item in results)
