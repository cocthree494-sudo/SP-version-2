"""Authentication API, rotation, hashing, and tenant-binding tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import cast
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.core.security import (
    create_access_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.db.base import Base
from app.db.session import get_db_session
from app.domains.auth.models import RefreshToken
from app.domains.auth.oauth import OAuthProfile
from app.domains.auth.repositories import RefreshTokenRepository
from app.domains.tenancy.models import ProviderIdentity, Tenant, TenantMembership, User
from app.domains.tenancy.repositories import UserRepository
from app.main import app


@pytest_asyncio.fixture
async def auth_session() -> AsyncGenerator[AsyncSession, None]:
    engine: AsyncEngine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )
    tables = [
        cast(Table, User.__table__),
        cast(Table, Tenant.__table__),
        cast(Table, TenantMembership.__table__),
        cast(Table, ProviderIdentity.__table__),
        cast(Table, RefreshToken.__table__),
    ]
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=tables)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def auth_client(auth_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        yield auth_session

    app.dependency_overrides[get_db_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


def registration_payload(
    *,
    email: str = "Owner@Example.com",
    organization_name: str = "Acme Support",
    organization_slug: str | None = None,
) -> dict[str, str]:
    payload = {
        "email": email,
        "password": "correct horse battery staple",
        "display_name": "Primary Owner",
        "organization_name": organization_name,
    }
    if organization_slug is not None:
        payload["organization_slug"] = organization_slug
    return payload


def test_passwords_use_argon2id_and_verify_safely() -> None:
    password_hash = hash_password("a sufficiently long password")

    assert password_hash.startswith("$argon2id$")
    assert "a sufficiently long password" not in password_hash
    assert verify_password("a sufficiently long password", password_hash) is True
    assert verify_password("wrong password", password_hash) is False
    assert verify_password("anything", "not-an-argon-hash") is False


@pytest.mark.asyncio
async def test_register_bootstraps_owner_and_me_context(
    auth_client: AsyncClient,
    auth_session: AsyncSession,
) -> None:
    response = await auth_client.post("/v1/auth/register", json=registration_payload())

    assert response.status_code == 201
    tokens = response.json()
    assert tokens["token_type"] == "bearer"  # noqa: S105 - OAuth token type
    assert tokens["expires_in"] > 0
    assert tokens["access_token"]
    assert tokens["refresh_token"].startswith("rt_")

    me_response = await auth_client.get(
        "/v1/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me_response.status_code == 200
    me = me_response.json()
    assert me["email"] == "owner@example.com"
    assert me["role"] == "owner"
    assert me["tenant"]["name"] == "Acme Support"
    assert me["tenant"]["slug"] == "acme-support"

    user = await UserRepository(auth_session).get_by_email("owner@example.com")
    assert user is not None
    assert user.password_hash is not None
    assert user.password_hash.startswith("$argon2id$")
    assert verify_password("correct horse battery staple", user.password_hash)

    stored_refresh = await auth_session.scalar(select(RefreshToken))
    assert stored_refresh is not None
    assert stored_refresh.token_hash == hash_refresh_token(tokens["refresh_token"])
    assert tokens["refresh_token"] not in stored_refresh.token_hash


@pytest.mark.asyncio
async def test_register_rejects_duplicate_identity_without_partial_bootstrap(
    auth_client: AsyncClient,
    auth_session: AsyncSession,
) -> None:
    first = await auth_client.post("/v1/auth/register", json=registration_payload())
    duplicate = await auth_client.post(
        "/v1/auth/register",
        json=registration_payload(
            email="owner@example.com",
            organization_name="Uncommitted Tenant",
            organization_slug="uncommitted-tenant",
        ),
    )

    assert first.status_code == 201
    assert duplicate.status_code == 409
    tenants = list(await auth_session.scalars(select(Tenant).order_by(Tenant.created_at)))
    assert [tenant.slug for tenant in tenants] == ["acme-support"]


@pytest.mark.asyncio
async def test_login_uses_generic_failure_and_accepts_normalized_email(
    auth_client: AsyncClient,
) -> None:
    await auth_client.post("/v1/auth/register", json=registration_payload())

    bad_response = await auth_client.post(
        "/v1/auth/login",
        json={"email": "missing@example.com", "password": "wrong-password"},
    )
    good_response = await auth_client.post(
        "/v1/auth/login",
        json={
            "email": "  OWNER@example.com ",
            "password": "correct horse battery staple",
            "organization_slug": "acme-support",
        },
    )

    assert bad_response.status_code == 401
    assert bad_response.headers["www-authenticate"] == "Bearer"
    assert bad_response.json()["detail"] == "Invalid email, password, or organization"
    assert good_response.status_code == 200
    assert good_response.json()["access_token"]


@pytest.mark.asyncio
async def test_refresh_rotation_rejects_reuse_and_revokes_family(
    auth_client: AsyncClient,
) -> None:
    register_response = await auth_client.post(
        "/v1/auth/register",
        json=registration_payload(),
    )
    original_refresh = register_response.json()["refresh_token"]

    rotated_response = await auth_client.post(
        "/v1/auth/refresh",
        json={"refresh_token": original_refresh},
    )
    assert rotated_response.status_code == 200
    replacement_refresh = rotated_response.json()["refresh_token"]
    assert replacement_refresh != original_refresh

    replay_response = await auth_client.post(
        "/v1/auth/refresh",
        json={"refresh_token": original_refresh},
    )
    assert replay_response.status_code == 401
    assert replay_response.json()["detail"] == "Refresh token reuse detected"

    revoked_replacement = await auth_client.post(
        "/v1/auth/refresh",
        json={"refresh_token": replacement_refresh},
    )
    assert revoked_replacement.status_code == 401


@pytest.mark.asyncio
async def test_access_token_cannot_switch_to_an_unowned_tenant(
    auth_client: AsyncClient,
    auth_session: AsyncSession,
) -> None:
    first_response = await auth_client.post(
        "/v1/auth/register",
        json=registration_payload(),
    )
    second_response = await auth_client.post(
        "/v1/auth/register",
        json=registration_payload(
            email="second@example.com",
            organization_name="Second Tenant",
            organization_slug="second-tenant",
        ),
    )
    first_me = await auth_client.get(
        "/v1/me",
        headers={"Authorization": f"Bearer {first_response.json()['access_token']}"},
    )
    second_me = await auth_client.get(
        "/v1/me",
        headers={"Authorization": f"Bearer {second_response.json()['access_token']}"},
    )
    cross_tenant_access, _ = create_access_token(
        UUID(first_me.json()["id"]),
        UUID(second_me.json()["tenant"]["id"]),
    )

    response = await auth_client.get(
        "/v1/me",
        headers={"Authorization": f"Bearer {cross_tenant_access}"},
    )
    assert response.status_code == 401

    first_tenant_id = UUID(first_me.json()["tenant"]["id"])
    second_refresh_hash = hash_refresh_token(second_response.json()["refresh_token"])
    cross_tenant_refresh = await RefreshTokenRepository(
        auth_session,
        first_tenant_id,
    ).get_for_rotation(second_refresh_hash)
    assert cross_tenant_refresh is None


@pytest.mark.asyncio
async def test_me_and_refresh_reject_missing_or_unknown_credentials(
    auth_client: AsyncClient,
) -> None:
    me_response = await auth_client.get("/v1/me")
    invalid_me_response = await auth_client.get(
        "/v1/me",
        headers={"Authorization": "Bearer not-a-valid-jwt"},
    )
    refresh_response = await auth_client.post(
        "/v1/auth/refresh",
        json={"refresh_token": "x" * 40},
    )

    assert me_response.status_code == 401
    assert invalid_me_response.status_code == 401
    assert refresh_response.status_code == 401


@pytest.mark.asyncio
async def test_social_registration_uses_one_time_pkce_state_and_creates_passwordless_identity(
    auth_client: AsyncClient,
    auth_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.domains.auth.service as auth_service
    from app.core.config import settings

    monkeypatch.setattr(settings, "OAUTH_GOOGLE_CLIENT_ID", "google-client")
    monkeypatch.setattr(settings, "OAUTH_GOOGLE_CLIENT_SECRET", SecretStr("google-secret"))

    async def fake_exchange(provider: str, *, code: str, oauth_state: object) -> OAuthProfile:
        assert provider == "google"
        assert code == "provider-code"
        return OAuthProfile(
            provider="google",
            issuer="https://accounts.google.com",
            subject="google-subject-1",
            email="social@example.com",
            email_verified=True,
            display_name="Social Owner",
        )

    monkeypatch.setattr(auth_service, "exchange_code", fake_exchange)
    start = await auth_client.post(
        "/v1/auth/oauth/google/start",
        json={"mode": "register"},
    )
    assert start.status_code == 200
    assert "code_challenge=" in start.json()["authorization_url"]
    from urllib.parse import parse_qs, urlparse

    state = parse_qs(urlparse(start.json()["authorization_url"]).query)["state"][0]
    callback = await auth_client.post(
        "/v1/auth/oauth/google/callback",
        json={"code": "provider-code", "state": state},
    )
    assert callback.status_code == 200
    callback_data = callback.json()
    assert callback_data["status"] == "organization_required"
    assert callback_data["continuation_token"]

    replay = await auth_client.post(
        "/v1/auth/oauth/google/callback",
        json={"code": "provider-code", "state": state},
    )
    assert replay.status_code == 401

    complete = await auth_client.post(
        "/v1/auth/oauth/register",
        json={
            "continuation_token": callback_data["continuation_token"],
            "organization_name": "Social Workspace",
        },
    )
    assert complete.status_code == 200
    assert complete.json()["access_token"]
    me = await auth_client.get(
        "/v1/me",
        headers={"Authorization": f"Bearer {complete.json()['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == "social@example.com"
    social_user = await UserRepository(auth_session).get_by_email("social@example.com")
    assert social_user is not None
    assert social_user.password_hash is None
