"""Voice-agent consent, cost controls, idempotency, and isolation tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any, cast
from uuid import uuid4

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

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db_session
from app.domains.auth.models import RefreshToken
from app.domains.tenancy.models import Tenant, TenantMembership, User
from app.domains.voice.models import VoiceAgentInstallation, VoiceWebhookEvent
from app.domains.voice.pipeline import normalize_voice_turn
from app.main import app
from tests.auth_helpers import register_with_otp


@pytest_asyncio.fixture
async def voice_session() -> AsyncGenerator[AsyncSession, None]:
    engine: AsyncEngine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    tables = [
        cast(Table, model.__table__)
        for model in (
            User,
            Tenant,
            TenantMembership,
            RefreshToken,
            VoiceAgentInstallation,
            VoiceWebhookEvent,
        )
    ]
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=tables)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def voice_client(voice_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        yield voice_session

    app.dependency_overrides[get_db_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


def bearer(tokens: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def register(client: AsyncClient, email: str, slug: str) -> dict[str, Any]:
    response = await register_with_otp(
        client,
        {
            "email": email,
            "password": "correct horse battery staple",
            "organization_name": "Voice Co",
            "organization_slug": slug,
        },
    )
    return cast(dict[str, Any], response.json())


@pytest.mark.asyncio
async def test_voice_setup_is_gated_until_an_adapter_exists(
    voice_client: AsyncClient,
) -> None:
    """No telephony adapter exists, so nothing may be presented as connected."""

    tokens = await register(voice_client, "gated@example.com", "gated-co")
    headers = bearer(tokens)
    assert settings.VOICE_AGENTS_ENABLED is False

    blocked = await voice_client.post(
        "/v1/voice",
        headers=headers,
        json={"phone_number": "+15550199", "consent_acknowledged": True},
    )
    assert blocked.status_code == 503
    assert "not available" in blocked.json()["detail"]

    patched = await voice_client.patch(
        f"/v1/voice/{uuid4()}", headers=headers, json={"status": "ready"}
    )
    assert patched.status_code == 503

    hooked = await voice_client.post(
        f"/v1/voice/{uuid4()}/webhooks",
        headers={"X-Provider-Signature": "x" * 64},
        json={"event_id": str(uuid4()), "event_type": "call.started", "payload": {}},
    )
    assert hooked.status_code == 503

    listed = await voice_client.get("/v1/voice", headers=headers)
    assert listed.status_code == 200
    assert listed.json() == []


@pytest.mark.asyncio
async def test_voice_defaults_are_private_and_consent_is_explicit(
    voice_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "VOICE_AGENTS_ENABLED", True)
    tokens = await register(voice_client, "voice@example.com", "voice-co")
    headers = bearer(tokens)
    missing_consent = await voice_client.post(
        "/v1/voice", headers=headers, json={"phone_number": "+15550101"}
    )
    assert missing_consent.status_code == 422
    outbound_without_consent = await voice_client.post(
        "/v1/voice",
        headers=headers,
        json={
            "phone_number": "+15550101",
            "consent_acknowledged": True,
            "outbound_enabled": True,
        },
    )
    assert outbound_without_consent.status_code == 422
    created = await voice_client.post(
        "/v1/voice",
        headers=headers,
        json={
            "phone_number": "+15550101",
            "consent_acknowledged": True,
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "pending"
    assert body["outbound_enabled"] is False
    assert body["recording_enabled"] is False
    assert body["retention_days"] == 0
    assert "provider_reference" not in body


@pytest.mark.asyncio
async def test_voice_webhook_requires_signature_and_is_idempotent(
    voice_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "VOICE_AGENTS_ENABLED", True)
    tokens = await register(voice_client, "hooks@example.com", "hooks-co")
    created = await voice_client.post(
        "/v1/voice",
        headers=bearer(tokens),
        json={
            "phone_number": "+15550102",
            "consent_acknowledged": True,
        },
    )
    voice_id = created.json()["id"]
    payload = {"event_id": str(uuid4()), "event_type": "call.started", "payload": {"call_id": "c1"}}
    missing = await voice_client.post(f"/v1/voice/{voice_id}/webhooks", json=payload)
    assert missing.status_code == 401
    headers = {"X-Provider-Signature": "x" * 64}
    first = await voice_client.post(f"/v1/voice/{voice_id}/webhooks", headers=headers, json=payload)
    second = await voice_client.post(
        f"/v1/voice/{voice_id}/webhooks", headers=headers, json=payload
    )
    assert first.status_code == second.status_code == 202


def test_voice_turn_normalization_supports_interruption() -> None:
    turn = normalize_voice_turn("  hello   there ", "  Hi   — how can I help? ", interrupted=True)
    assert turn.transcript == "hello there"
    assert turn.response_text == "Hi — how can I help?"
    assert turn.should_interrupt is True
