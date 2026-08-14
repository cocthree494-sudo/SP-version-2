"""Channel installation policy, consent, and tenant isolation tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any, cast

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Table, select
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
from app.domains.bots.models import Bot
from app.domains.channels.models import ChannelInstallation
from app.domains.tenancy.enums import MembershipRole
from app.domains.tenancy.models import Tenant, TenantMembership, User
from app.main import app


@pytest_asyncio.fixture
async def channel_session() -> AsyncGenerator[AsyncSession, None]:
    engine: AsyncEngine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    tables = [
        cast(Table, User.__table__),
        cast(Table, Tenant.__table__),
        cast(Table, TenantMembership.__table__),
        cast(Table, RefreshToken.__table__),
        cast(Table, Bot.__table__),
        cast(Table, ChannelInstallation.__table__),
    ]
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=tables)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def channel_client(channel_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        yield channel_session

    app.dependency_overrides[get_db_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


def bearer(tokens: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def register(client: AsyncClient, email: str, organization_slug: str) -> dict[str, Any]:
    response = await client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": "correct horse battery staple",
            "organization_name": "Channel Co",
            "organization_slug": organization_slug,
        },
    )
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


async def create_bot(client: AsyncClient, tokens: dict[str, Any], name: str = "Channel Bot") -> str:
    response = await client.post(
        "/v1/bots",
        headers=bearer(tokens),
        json={"name": name},
    )
    assert response.status_code == 201
    return cast(str, response.json()["id"])


@pytest.mark.asyncio
async def test_channel_installation_requires_consent_and_approved_identity(
    channel_client: AsyncClient,
) -> None:
    tokens = await register(channel_client, "owner@example.com", "channel-co")
    headers = bearer(tokens)
    bot_id = await create_bot(channel_client, tokens)

    missing_consent = await channel_client.post(
        "/v1/channels",
        headers=headers,
        json={
            "channel_type": "telegram_personal",
            "bot_id": bot_id,
            "external_identity": "telegram:123",
        },
    )
    assert missing_consent.status_code == 422
    assert "consent" in missing_consent.json()["detail"][0]["msg"].lower()

    personal_whatsapp = await channel_client.post(
        "/v1/channels",
        headers=headers,
        json={
            "channel_type": "whatsapp_business",
            "bot_id": bot_id,
            "external_identity": "personal:123",
            "consent_acknowledged": True,
        },
    )
    assert personal_whatsapp.status_code == 422

    created = await channel_client.post(
        "/v1/channels",
        headers=headers,
        json={
            "channel_type": "telegram_personal",
            "bot_id": bot_id,
            "external_identity": "telegram:123",
            "conversation_scope": ["dm:456"],
            "consent_acknowledged": True,
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "pending"
    assert body["bot_id"] == bot_id
    assert body["consent_record"]["acknowledged"] is True
    assert "credential_reference" not in body

    listed = await channel_client.get("/v1/channels", headers=headers)
    assert listed.status_code == 200
    assert listed.json()[0]["external_identity"] == "telegram:123"


@pytest.mark.asyncio
async def test_channel_isolation_and_revoke_clears_connection(
    channel_client: AsyncClient,
) -> None:
    first = await register(channel_client, "first@example.com", "first-co")
    second = await register(channel_client, "second@example.com", "second-co")
    first_headers = bearer(first)
    second_headers = bearer(second)
    first_bot_id = await create_bot(channel_client, first, "First Bot")
    second_bot_id = await create_bot(channel_client, second, "Second Bot")

    created = await channel_client.post(
        "/v1/channels",
        headers=first_headers,
        json={
            "channel_type": "facebook_page",
            "bot_id": first_bot_id,
            "external_identity": "page:789",
            "consent_acknowledged": True,
        },
    )
    assert created.status_code == 201
    channel_id = created.json()["id"]

    hidden = await channel_client.get("/v1/channels", headers=second_headers)
    assert hidden.status_code == 200
    assert hidden.json() == []

    cross_tenant = await channel_client.patch(
        f"/v1/channels/{channel_id}",
        headers=second_headers,
        json={"status": "paused"},
    )
    assert cross_tenant.status_code == 404

    foreign_bot = await channel_client.patch(
        f"/v1/channels/{channel_id}",
        headers=first_headers,
        json={"bot_id": second_bot_id},
    )
    assert foreign_bot.status_code == 404

    revoked = await channel_client.delete(f"/v1/channels/{channel_id}", headers=first_headers)
    assert revoked.status_code == 204
    assert (await channel_client.get("/v1/channels", headers=first_headers)).json()[0][
        "status"
    ] == "revoked"


@pytest.mark.asyncio
async def test_member_cannot_install_channels(
    channel_client: AsyncClient,
    channel_session: AsyncSession,
) -> None:
    tokens = await register(channel_client, "owner@example.com", "member-co")
    bot_id = await create_bot(channel_client, tokens)
    user = await channel_session.scalar(select(User).where(User.email == "owner@example.com"))
    assert user is not None
    membership = await channel_session.scalar(
        select(TenantMembership).where(TenantMembership.user_id == user.id)
    )
    assert membership is not None
    membership.role = MembershipRole.MEMBER
    await channel_session.commit()
    response = await channel_client.post(
        "/v1/channels",
        headers=bearer(tokens),
        json={
            "channel_type": "email",
            "bot_id": bot_id,
            "external_identity": "support@example.com",
            "consent_acknowledged": True,
        },
    )
    assert response.status_code == 403
