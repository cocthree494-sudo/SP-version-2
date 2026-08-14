"""Append-only usage accounting, summaries, and tenant isolation tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.domains.auth.models import RefreshToken
from app.domains.bots.models import Bot, BotKey
from app.domains.tenancy.models import Tenant, TenantMembership, User
from app.domains.usage.enums import UsageOperation
from app.domains.usage.models import UsageEvent, UsageEventMutationError
from app.domains.usage.schemas import UsageRecordInput
from app.domains.usage.service import UsageBotNotFoundError, UsageService
from app.main import app
from tests.auth_helpers import register_with_otp


@pytest_asyncio.fixture
async def usage_session() -> AsyncGenerator[AsyncSession, None]:
    engine: AsyncEngine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )
    tables = [
        cast(Table, User.__table__),
        cast(Table, Tenant.__table__),
        cast(Table, TenantMembership.__table__),
        cast(Table, RefreshToken.__table__),
        cast(Table, Bot.__table__),
        cast(Table, BotKey.__table__),
        cast(Table, UsageEvent.__table__),
    ]
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=tables)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def usage_client(usage_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        yield usage_session

    app.dependency_overrides[get_db_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


async def register_with_bot(
    client: AsyncClient,
    *,
    email: str,
    organization_name: str,
    organization_slug: str,
) -> tuple[dict[str, Any], dict[str, Any], UUID]:
    register_response = await register_with_otp(
        client,
        {
            "email": email,
            "password": "correct horse battery staple",
            "organization_name": organization_name,
            "organization_slug": organization_slug,
        },
    )
    tokens = cast(dict[str, Any], register_response.json())
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    bot_response = await client.post(
        "/v1/bots",
        headers=headers,
        json={"name": f"{organization_name} Bot"},
    )
    me_response = await client.get("/v1/me", headers=headers)
    assert bot_response.status_code == 201
    assert me_response.status_code == 200
    tenant_id = UUID(me_response.json()["tenant"]["id"])
    return tokens, cast(dict[str, Any], bot_response.json()), tenant_id


def auth_headers(tokens: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.mark.asyncio
async def test_usage_summary_normalizes_and_aggregates_exact_units(
    usage_client: AsyncClient,
    usage_session: AsyncSession,
) -> None:
    tokens, bot, tenant_id = await register_with_bot(
        usage_client,
        email="owner@example.com",
        organization_name="Acme",
        organization_slug="acme",
    )
    service = UsageService(usage_session, tenant_id)
    await service.record(
        UsageRecordInput(
            bot_id=UUID(bot["id"]),
            operation=UsageOperation.GENERATION,
            provider=" OpenAI ",
            model="configured-small-model",
            input_tokens=100,
            output_tokens=40,
            cache_read_tokens=20,
            latency_ms=120,
            estimated_cost_microusd=35,
        )
    )
    await service.record(
        UsageRecordInput(
            bot_id=UUID(bot["id"]),
            operation=UsageOperation.GENERATION,
            provider="openai",
            model="configured-small-model",
            input_tokens=60,
            output_tokens=20,
            cache_write_tokens=10,
            latency_ms=80,
            estimated_cost_microusd=15,
        )
    )
    await usage_session.commit()

    response = await usage_client.get(
        "/v1/usage/summary",
        headers=auth_headers(tokens),
    )
    assert response.status_code == 200
    summary = response.json()
    assert summary["event_count"] == 2
    assert summary["input_tokens"] == 160
    assert summary["output_tokens"] == 60
    assert summary["cache_read_tokens"] == 20
    assert summary["cache_write_tokens"] == 10
    assert summary["total_tokens"] == 220
    assert summary["total_latency_ms"] == 200
    assert summary["average_latency_ms"] == 100.0
    assert summary["estimated_cost_microusd"] == 50
    assert len(summary["by_model"]) == 1
    assert summary["by_model"][0]["provider"] == "openai"


@pytest.mark.asyncio
async def test_usage_summary_filters_by_half_open_utc_period(
    usage_client: AsyncClient,
    usage_session: AsyncSession,
) -> None:
    tokens, bot, tenant_id = await register_with_bot(
        usage_client,
        email="owner@example.com",
        organization_name="Acme",
        organization_slug="acme",
    )
    service = UsageService(usage_session, tenant_id)
    for occurred_at, tokens_used in (
        (datetime(2026, 1, 1, tzinfo=UTC), 10),
        (datetime(2026, 2, 1, tzinfo=UTC), 20),
    ):
        await service.record(
            UsageRecordInput(
                bot_id=UUID(bot["id"]),
                operation=UsageOperation.EMBEDDING,
                provider="provider-a",
                model="embedding-model",
                input_tokens=tokens_used,
                created_at=occurred_at,
            )
        )
    await usage_session.commit()

    response = await usage_client.get(
        "/v1/usage/summary",
        headers=auth_headers(tokens),
        params={
            "start": "2026-01-01T00:00:00Z",
            "end": "2026-02-01T00:00:00Z",
            "bot_id": bot["id"],
        },
    )
    invalid_range = await usage_client.get(
        "/v1/usage/summary",
        headers=auth_headers(tokens),
        params={"start": "2026-02-01T00:00:00Z", "end": "2026-01-01T00:00:00Z"},
    )
    naive_boundary = await usage_client.get(
        "/v1/usage/summary",
        headers=auth_headers(tokens),
        params={"start": "2026-01-01T00:00:00"},
    )

    assert response.status_code == 200
    assert response.json()["event_count"] == 1
    assert response.json()["input_tokens"] == 10
    assert invalid_range.status_code == 422
    assert naive_boundary.status_code == 422


@pytest.mark.asyncio
async def test_usage_summaries_and_bot_validation_are_tenant_isolated(
    usage_client: AsyncClient,
    usage_session: AsyncSession,
) -> None:
    first_tokens, first_bot, first_tenant = await register_with_bot(
        usage_client,
        email="first@example.com",
        organization_name="First",
        organization_slug="first",
    )
    second_tokens, second_bot, second_tenant = await register_with_bot(
        usage_client,
        email="second@example.com",
        organization_name="Second",
        organization_slug="second",
    )
    await UsageService(usage_session, first_tenant).record(
        UsageRecordInput(
            bot_id=UUID(first_bot["id"]),
            operation=UsageOperation.GENERATION,
            provider="provider-a",
            model="model-a",
            input_tokens=11,
        )
    )
    await UsageService(usage_session, second_tenant).record(
        UsageRecordInput(
            bot_id=UUID(second_bot["id"]),
            operation=UsageOperation.GENERATION,
            provider="provider-b",
            model="model-b",
            input_tokens=22,
        )
    )
    await usage_session.commit()

    first_summary = await usage_client.get(
        "/v1/usage/summary",
        headers=auth_headers(first_tokens),
    )
    second_summary = await usage_client.get(
        "/v1/usage/summary",
        headers=auth_headers(second_tokens),
    )
    assert first_summary.json()["input_tokens"] == 11
    assert second_summary.json()["input_tokens"] == 22

    with pytest.raises(UsageBotNotFoundError):
        await UsageService(usage_session, first_tenant).record(
            UsageRecordInput(
                bot_id=UUID(second_bot["id"]),
                operation=UsageOperation.GENERATION,
                provider="provider-a",
                model="model-a",
            )
        )
    await usage_session.rollback()


@pytest.mark.asyncio
async def test_usage_events_reject_orm_update_and_delete(
    usage_client: AsyncClient,
    usage_session: AsyncSession,
) -> None:
    _tokens, bot, tenant_id = await register_with_bot(
        usage_client,
        email="owner@example.com",
        organization_name="Acme",
        organization_slug="acme",
    )
    event = await UsageService(usage_session, tenant_id).record(
        UsageRecordInput(
            bot_id=UUID(bot["id"]),
            operation=UsageOperation.GENERATION,
            provider="provider-a",
            model="model-a",
            input_tokens=1,
        )
    )
    await usage_session.commit()
    event_id = event.id

    event.input_tokens = 999
    with pytest.raises(UsageEventMutationError):
        await usage_session.commit()
    await usage_session.rollback()

    persisted = await usage_session.get(UsageEvent, event_id)
    assert persisted is not None
    await usage_session.delete(persisted)
    with pytest.raises(UsageEventMutationError):
        await usage_session.commit()
    await usage_session.rollback()


def test_usage_record_rejects_negative_values() -> None:
    with pytest.raises(ValidationError):
        UsageRecordInput(
            operation=UsageOperation.GENERATION,
            provider="provider-a",
            model="model-a",
            input_tokens=-1,
        )
