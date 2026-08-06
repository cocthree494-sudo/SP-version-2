"""Public widget session, CORS, SSE, revocation, and rate-limit tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import cast

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.api.widget import get_model_circuit_store, get_widget_rate_limiter
from app.core.config import settings
from app.db.base import Base, utc_now
from app.db.session import get_db_session
from app.domains.bots.models import Bot, BotKey
from app.domains.bots.service import generate_publishable_key
from app.domains.chat.models import Conversation, ConversationMessage
from app.domains.chat.rate_limit import InMemoryRateLimiter
from app.domains.chat.widget_sessions import decode_widget_session_token
from app.domains.knowledge.models import Document, DocumentChunk, KnowledgeSource
from app.domains.provider_access.models import ProviderPolicy
from app.domains.tenancy.models import Tenant
from app.domains.usage.models import UsageEvent
from app.main import app
from app.providers.router import InMemoryCircuitStore

ALLOWED_ORIGIN = "https://shop.example"


@pytest_asyncio.fixture
async def widget_session() -> AsyncGenerator[AsyncSession, None]:
    engine: AsyncEngine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )
    tables = [
        cast(Table, Tenant.__table__),
        cast(Table, Bot.__table__),
        cast(Table, BotKey.__table__),
        cast(Table, Conversation.__table__),
        cast(Table, ConversationMessage.__table__),
        cast(Table, UsageEvent.__table__),
        cast(Table, KnowledgeSource.__table__),
        cast(Table, Document.__table__),
        cast(Table, DocumentChunk.__table__),
        cast(Table, ProviderPolicy.__table__),
    ]
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=tables)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def widget_client(
    widget_session: AsyncSession,
) -> AsyncGenerator[tuple[AsyncClient, BotKey], None]:
    tenant = Tenant(name="Widget", slug="widget")
    widget_session.add(tenant)
    await widget_session.flush()
    bot = Bot(tenant_id=tenant.id, name="Widget support", default_language="auto")
    widget_session.add(bot)
    await widget_session.flush()
    key = BotKey(
        tenant_id=tenant.id,
        bot_id=bot.id,
        publishable_key=generate_publishable_key(tenant.id),
        label="Public",
        allowed_origins=[ALLOWED_ORIGIN],
    )
    widget_session.add(key)
    await widget_session.commit()

    limiter = InMemoryRateLimiter()
    circuits = InMemoryCircuitStore()

    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        yield widget_session

    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_widget_rate_limiter] = lambda: limiter
    app.dependency_overrides[get_model_circuit_store] = lambda: circuits
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, key
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_widget_session_and_sse_chat_enforce_exact_origin(
    widget_client: tuple[AsyncClient, BotKey],
) -> None:
    client, key = widget_client
    preflight = await client.options(
        f"/v1/widget/{key.publishable_key}/sessions",
        headers={"Origin": ALLOWED_ORIGIN},
    )
    wrong_preflight = await client.options(
        f"/v1/widget/{key.publishable_key}/sessions",
        headers={"Origin": "https://attacker.example"},
    )
    assert preflight.status_code == 204
    assert preflight.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert wrong_preflight.status_code == 403

    created = await client.post(
        f"/v1/widget/{key.publishable_key}/sessions",
        headers={"Origin": ALLOWED_ORIGIN},
    )
    assert created.status_code == 201
    assert created.headers["cache-control"] == "no-store"
    session_payload = created.json()
    claims = decode_widget_session_token(session_payload["session_token"])
    assert str(claims.conversation_id) == session_payload["conversation_id"]
    assert claims.origin == ALLOWED_ORIGIN

    streamed = await client.post(
        f"/v1/widget/{key.publishable_key}/messages",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Authorization": f"Bearer {session_payload['session_token']}",
        },
        json={"message": "What is your refund policy?"},
    )
    assert streamed.status_code == 200
    assert streamed.headers["content-type"].startswith("text/event-stream")
    assert streamed.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert "event: ready" in streamed.text
    assert "event: text_delta" in streamed.text
    assert "event: completed" in streamed.text
    assert "I don't know based on the available information" in streamed.text

    wrong_origin = await client.post(
        f"/v1/widget/{key.publishable_key}/messages",
        headers={
            "Origin": "https://attacker.example",
            "Authorization": f"Bearer {session_payload['session_token']}",
        },
        json={"message": "Steal context"},
    )
    assert wrong_origin.status_code == 401


@pytest.mark.asyncio
async def test_revocation_invalidates_existing_widget_session(
    widget_client: tuple[AsyncClient, BotKey],
    widget_session: AsyncSession,
) -> None:
    client, key = widget_client
    created = await client.post(
        f"/v1/widget/{key.publishable_key}/sessions",
        headers={"Origin": ALLOWED_ORIGIN},
    )
    token = created.json()["session_token"]
    key.revoked_at = utc_now()
    await widget_session.commit()

    response = await client.post(
        f"/v1/widget/{key.publishable_key}/messages",
        headers={"Origin": ALLOWED_ORIGIN, "Authorization": f"Bearer {token}"},
        json={"message": "Still there?"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_widget_session_creation_is_rate_limited(
    widget_client: tuple[AsyncClient, BotKey],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, key = widget_client
    monkeypatch.setattr(settings, "WIDGET_SESSION_RATE_LIMIT", 1)
    first = await client.post(
        f"/v1/widget/{key.publishable_key}/sessions",
        headers={"Origin": ALLOWED_ORIGIN},
    )
    second = await client.post(
        f"/v1/widget/{key.publishable_key}/sessions",
        headers={"Origin": ALLOWED_ORIGIN},
    )
    assert first.status_code == 201
    assert second.status_code == 429
    assert int(second.headers["retry-after"]) >= 1
