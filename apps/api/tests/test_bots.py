"""Bot CRUD, widget credentials, permissions, and tenant isolation tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any, cast
from uuid import UUID

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

from app.core.security import create_access_token
from app.db.base import Base
from app.db.session import get_db_session
from app.domains.auth.models import RefreshToken
from app.domains.bots.models import Bot, BotKey
from app.domains.bots.service import resolve_widget_credential
from app.domains.tenancy.enums import MembershipRole
from app.domains.tenancy.models import Tenant, TenantMembership, User
from app.domains.tenancy.repositories import MembershipRepository, UserRepository
from app.main import app


@pytest_asyncio.fixture
async def bot_session() -> AsyncGenerator[AsyncSession, None]:
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
    ]
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=tables)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def bot_client(bot_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        yield bot_session

    app.dependency_overrides[get_db_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


async def register_owner(
    client: AsyncClient,
    *,
    email: str = "owner@example.com",
    organization_name: str = "Acme",
    organization_slug: str = "acme",
) -> dict[str, Any]:
    response = await client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": "correct horse battery staple",
            "organization_name": organization_name,
            "organization_slug": organization_slug,
        },
    )
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


def bearer(tokens: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def create_bot(client: AsyncClient, tokens: dict[str, Any]) -> dict[str, Any]:
    response = await client.post(
        "/v1/bots",
        headers=bearer(tokens),
        json={
            "name": "Help Bot",
            "system_policy": "Answer only from approved knowledge.",
            "default_language": "BN",
        },
    )
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


@pytest.mark.asyncio
async def test_owner_can_create_read_update_and_delete_bot(bot_client: AsyncClient) -> None:
    tokens = await register_owner(bot_client)
    created = await create_bot(bot_client, tokens)

    assert created["name"] == "Help Bot"
    assert created["default_language"] == "bn"
    assert created["status"] == "active"

    list_response = await bot_client.get("/v1/bots", headers=bearer(tokens))
    get_response = await bot_client.get(
        f"/v1/bots/{created['id']}",
        headers=bearer(tokens),
    )
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [created["id"]]
    assert get_response.status_code == 200

    patch_response = await bot_client.patch(
        f"/v1/bots/{created['id']}",
        headers=bearer(tokens),
        json={"name": "Updated Bot", "status": "disabled", "system_policy": None},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["name"] == "Updated Bot"
    assert patch_response.json()["status"] == "disabled"
    assert patch_response.json()["system_policy"] is None

    empty_patch = await bot_client.patch(
        f"/v1/bots/{created['id']}",
        headers=bearer(tokens),
        json={},
    )
    assert empty_patch.status_code == 422

    delete_response = await bot_client.delete(
        f"/v1/bots/{created['id']}",
        headers=bearer(tokens),
    )
    missing_response = await bot_client.get(
        f"/v1/bots/{created['id']}",
        headers=bearer(tokens),
    )
    assert delete_response.status_code == 204
    assert missing_response.status_code == 404


@pytest.mark.asyncio
async def test_widget_keys_normalize_origins_resolve_and_revoke(
    bot_client: AsyncClient,
    bot_session: AsyncSession,
) -> None:
    tokens = await register_owner(bot_client)
    bot = await create_bot(bot_client, tokens)
    create_response = await bot_client.post(
        f"/v1/bots/{bot['id']}/keys",
        headers=bearer(tokens),
        json={
            "label": "Production",
            "allowed_origins": [
                "HTTPS://Example.COM:443/",
                "https://example.com",
                "http://localhost:3000",
            ],
        },
    )

    assert create_response.status_code == 201
    key = create_response.json()
    assert key["publishable_key"].startswith("pk_")
    assert key["allowed_origins"] == ["https://example.com", "http://localhost:3000"]
    assert key["revoked_at"] is None

    list_response = await bot_client.get(
        f"/v1/bots/{bot['id']}/keys",
        headers=bearer(tokens),
    )
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [key["id"]]

    resolved = await resolve_widget_credential(
        bot_session,
        publishable_key=key["publishable_key"],
        origin="https://EXAMPLE.com:443",
    )
    wrong_origin = await resolve_widget_credential(
        bot_session,
        publishable_key=key["publishable_key"],
        origin="https://attacker.example",
    )
    assert resolved is not None
    assert str(resolved.bot_id) == bot["id"]
    assert wrong_origin is None

    disable_response = await bot_client.patch(
        f"/v1/bots/{bot['id']}",
        headers=bearer(tokens),
        json={"status": "disabled"},
    )
    disabled_resolution = await resolve_widget_credential(
        bot_session,
        publishable_key=key["publishable_key"],
        origin="https://example.com",
    )
    assert disable_response.status_code == 200
    assert disabled_resolution is None

    await bot_client.patch(
        f"/v1/bots/{bot['id']}",
        headers=bearer(tokens),
        json={"status": "active"},
    )
    update_response = await bot_client.patch(
        f"/v1/bots/{bot['id']}/keys/{key['id']}",
        headers=bearer(tokens),
        json={"allowed_origins": ["https://support.example.com/"]},
    )
    assert update_response.status_code == 200
    assert update_response.json()["allowed_origins"] == ["https://support.example.com"]
    old_origin_after_update = await resolve_widget_credential(
        bot_session,
        publishable_key=key["publishable_key"],
        origin="https://example.com",
    )
    new_origin_after_update = await resolve_widget_credential(
        bot_session,
        publishable_key=key["publishable_key"],
        origin="https://support.example.com",
    )
    assert old_origin_after_update is None
    assert new_origin_after_update is not None

    revoke_response = await bot_client.delete(
        f"/v1/bots/{bot['id']}/keys/{key['id']}",
        headers=bearer(tokens),
    )
    revoked_resolution = await resolve_widget_credential(
        bot_session,
        publishable_key=key["publishable_key"],
        origin="https://support.example.com",
    )
    revoked_update = await bot_client.patch(
        f"/v1/bots/{bot['id']}/keys/{key['id']}",
        headers=bearer(tokens),
        json={"label": "Cannot change"},
    )
    assert revoke_response.status_code == 204
    assert revoked_resolution is None
    assert revoked_update.status_code == 409

    repeated_revoke = await bot_client.delete(
        f"/v1/bots/{bot['id']}/keys/{key['id']}",
        headers=bearer(tokens),
    )
    assert repeated_revoke.status_code == 204


@pytest.mark.asyncio
async def test_invalid_widget_origins_are_rejected(bot_client: AsyncClient) -> None:
    tokens = await register_owner(bot_client)
    bot = await create_bot(bot_client, tokens)

    for invalid_origin in (
        "*",
        "javascript://example.com",
        "https://example.com/path",
        "https://user:password@example.com",
    ):
        response = await bot_client.post(
            f"/v1/bots/{bot['id']}/keys",
            headers=bearer(tokens),
            json={"allowed_origins": [invalid_origin]},
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_bot_and_key_queries_cannot_cross_tenants(bot_client: AsyncClient) -> None:
    first_tokens = await register_owner(bot_client)
    first_bot = await create_bot(bot_client, first_tokens)
    first_key_response = await bot_client.post(
        f"/v1/bots/{first_bot['id']}/keys",
        headers=bearer(first_tokens),
        json={"allowed_origins": ["https://first.example"]},
    )
    assert first_key_response.status_code == 201

    second_tokens = await register_owner(
        bot_client,
        email="second@example.com",
        organization_name="Second",
        organization_slug="second",
    )
    second_list = await bot_client.get("/v1/bots", headers=bearer(second_tokens))
    second_get = await bot_client.get(
        f"/v1/bots/{first_bot['id']}",
        headers=bearer(second_tokens),
    )
    second_update = await bot_client.patch(
        f"/v1/bots/{first_bot['id']}",
        headers=bearer(second_tokens),
        json={"name": "Cross-tenant write"},
    )
    second_keys = await bot_client.get(
        f"/v1/bots/{first_bot['id']}/keys",
        headers=bearer(second_tokens),
    )

    assert second_list.status_code == 200
    assert second_list.json() == []
    assert second_get.status_code == 404
    assert second_update.status_code == 404
    assert second_keys.status_code == 404

    first_get = await bot_client.get(
        f"/v1/bots/{first_bot['id']}",
        headers=bearer(first_tokens),
    )
    assert first_get.status_code == 200
    assert first_get.json()["name"] == "Help Bot"


@pytest.mark.asyncio
async def test_member_can_read_but_cannot_manage_bots(
    bot_client: AsyncClient,
    bot_session: AsyncSession,
) -> None:
    owner_tokens = await register_owner(bot_client)
    bot = await create_bot(bot_client, owner_tokens)
    owner_me = await bot_client.get("/v1/me", headers=bearer(owner_tokens))
    tenant_id = UUID(owner_me.json()["tenant"]["id"])

    member = await UserRepository(bot_session).create(
        email="member@example.com",
        password_hash="unused-test-hash",  # noqa: S106 - non-secret fixture value
    )
    await MembershipRepository(bot_session, tenant_id).create(
        user_id=member.id,
        role=MembershipRole.MEMBER,
    )
    await bot_session.commit()
    member_access_token, _ = create_access_token(member.id, tenant_id)
    member_headers = {"Authorization": f"Bearer {member_access_token}"}

    list_response = await bot_client.get("/v1/bots", headers=member_headers)
    create_response = await bot_client.post(
        "/v1/bots",
        headers=member_headers,
        json={"name": "Forbidden"},
    )
    update_response = await bot_client.patch(
        f"/v1/bots/{bot['id']}",
        headers=member_headers,
        json={"name": "Forbidden"},
    )
    key_response = await bot_client.post(
        f"/v1/bots/{bot['id']}/keys",
        headers=member_headers,
        json={"allowed_origins": ["https://example.com"]},
    )

    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert create_response.status_code == 403
    assert update_response.status_code == 403
    assert key_response.status_code == 403
