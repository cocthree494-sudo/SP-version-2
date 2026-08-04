"""Conversation ordering, compaction, retention, and tenant isolation tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Sequence
from datetime import UTC, datetime, timedelta
from typing import cast

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
from app.domains.bots.models import Bot
from app.domains.chat.conversation_service import (
    ConversationNotFoundError,
    ConversationService,
)
from app.domains.chat.enums import ConversationMessageRole
from app.domains.chat.models import Conversation, ConversationMessage
from app.domains.tenancy.models import Tenant


@pytest_asyncio.fixture
async def conversation_session() -> AsyncGenerator[AsyncSession, None]:
    engine: AsyncEngine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )
    tables = [
        cast(Table, Tenant.__table__),
        cast(Table, Bot.__table__),
        cast(Table, Conversation.__table__),
        cast(Table, ConversationMessage.__table__),
    ]
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=tables)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def seed_bot(session: AsyncSession, slug: str) -> tuple[Tenant, Bot]:
    tenant = Tenant(name=slug.title(), slug=slug)
    session.add(tenant)
    await session.flush()
    bot = Bot(tenant_id=tenant.id, name=f"{slug.title()} bot", default_language="auto")
    session.add(bot)
    await session.flush()
    return tenant, bot


class RecordingSummarizer:
    def __init__(self) -> None:
        self.calls: list[tuple[str | None, list[int]]] = []

    async def summarize(
        self,
        *,
        existing_summary: str | None,
        messages: Sequence[ConversationMessage],
    ) -> str:
        sequences = [message.sequence for message in messages]
        self.calls.append((existing_summary, sequences))
        prefix = f"{existing_summary} | " if existing_summary else ""
        return f"{prefix}turns {sequences}"


class RecordingRetentionHook:
    def __init__(self) -> None:
        self.conversation_ids: list[str] = []

    async def before_purge(self, conversation: Conversation) -> None:
        self.conversation_ids.append(str(conversation.id))


@pytest.mark.asyncio
async def test_recent_window_and_rolling_summary_are_incremental(
    conversation_session: AsyncSession,
) -> None:
    tenant, bot = await seed_bot(conversation_session, "acme")
    service = ConversationService(conversation_session, tenant.id)
    conversation = await service.create(bot_id=bot.id, channel="Widget")
    for index in range(1, 6):
        await service.append_message(
            conversation.id,
            role=(
                ConversationMessageRole.USER
                if index % 2
                else ConversationMessageRole.ASSISTANT
            ),
            content=f"message {index}",
        )

    summarizer = RecordingSummarizer()
    assert await service.compact(conversation.id, summarizer, keep_recent=2) is True
    context = await service.load_context(conversation.id, recent_limit=2)

    assert context.summary == "turns [1, 2, 3]"
    assert context.conversation.summary_through_sequence == 3
    assert [message.sequence for message in context.recent_messages] == [4, 5]
    assert summarizer.calls == [(None, [1, 2, 3])]

    for index in range(6, 8):
        await service.append_message(
            conversation.id,
            role=ConversationMessageRole.USER,
            content=f"message {index}",
        )
    assert await service.compact(conversation.id, summarizer, keep_recent=2) is True
    assert summarizer.calls[-1] == ("turns [1, 2, 3]", [4, 5])
    second_context = await service.load_context(conversation.id, recent_limit=2)
    assert [message.sequence for message in second_context.recent_messages] == [6, 7]


@pytest.mark.asyncio
async def test_conversation_reads_writes_and_retention_are_tenant_isolated(
    conversation_session: AsyncSession,
) -> None:
    first_tenant, first_bot = await seed_bot(conversation_session, "first")
    second_tenant, second_bot = await seed_bot(conversation_session, "second")
    old = datetime.now(UTC) - timedelta(days=60)
    first_service = ConversationService(conversation_session, first_tenant.id)
    second_service = ConversationService(conversation_session, second_tenant.id)
    first = await first_service.create(bot_id=first_bot.id, channel="widget", now=old)
    second = await second_service.create(bot_id=second_bot.id, channel="widget", now=old)
    await first_service.append_message(
        first.id,
        role=ConversationMessageRole.USER,
        content="first tenant secret",
        now=old,
    )
    await second_service.append_message(
        second.id,
        role=ConversationMessageRole.USER,
        content="second tenant secret",
        now=old,
    )

    with pytest.raises(ConversationNotFoundError):
        await first_service.load_context(second.id)
    with pytest.raises(ConversationNotFoundError):
        await first_service.append_message(
            second.id,
            role=ConversationMessageRole.USER,
            content="cross-tenant write",
        )

    hook = RecordingRetentionHook()
    assert await first_service.purge_expired(before=datetime.now(UTC), hook=hook) == 1
    assert hook.conversation_ids == [str(first.id)]
    assert await second_service.load_context(second.id)
    assert await second_service.purge_expired(before=datetime.now(UTC)) == 1


@pytest.mark.asyncio
async def test_conversation_requires_bot_from_same_tenant(
    conversation_session: AsyncSession,
) -> None:
    first_tenant, _first_bot = await seed_bot(conversation_session, "first")
    _second_tenant, second_bot = await seed_bot(conversation_session, "second")

    with pytest.raises(ConversationNotFoundError):
        await ConversationService(conversation_session, first_tenant.id).create(
            bot_id=second_bot.id,
            channel="dashboard",
        )

