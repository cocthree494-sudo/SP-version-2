"""Encrypted tenant BYOK lifecycle, authorization, redaction, and routing tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any, cast
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

from app.api.providers import get_credential_verifier, get_provider_envelope_cipher
from app.core.envelope import EnvelopeCipher, LocalAesGcmKeyWrapper
from app.core.security import create_access_token
from app.db.base import Base
from app.db.session import get_db_session
from app.domains.auth.models import RefreshToken
from app.domains.provider_access.catalog import (
    HERMES_PROVIDER_SOURCE_REVISION,
    PROVIDER_CATALOG,
    provider_catalog,
)
from app.domains.provider_access.enums import GenerationProvider, ProviderRoutingMode
from app.domains.provider_access.models import ProviderCredential, ProviderPolicy
from app.domains.tenancy.enums import MembershipRole
from app.domains.tenancy.models import Tenant, TenantMembership, User
from app.domains.tenancy.repositories import MembershipRepository, UserRepository
from app.main import app
from app.providers.openai_compatible import OpenAICompatibleLLMProvider
from app.providers.router import ModelTier
from app.providers.tenant_factory import (
    _APPROVED_BASE_URLS,
    TenantProviderUnavailableError,
    build_tenant_llm_targets,
)
from app.providers.types import ProviderError, ProviderErrorCategory
from tests.auth_helpers import register_with_otp

RAW_KEY = "sk-test-tenant-secret-never-exposed-1234"
ROTATED_KEY = "sk-test-rotated-secret-never-exposed-5678"


@pytest.mark.asyncio
async def test_provider_catalog_is_complete_and_only_ready_adapters_are_selectable(
    provider_client: tuple[AsyncClient, EnvelopeCipher, RecordingVerifier],
) -> None:
    client, _cipher, _verifier = provider_client
    tokens = await register_owner(client)

    response = await client.get("/v1/providers/catalog", headers=bearer(tokens))

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == len(PROVIDER_CATALOG)
    assert {entry["id"] for entry in payload} >= {
        "openai",
        "gemini",
        "anthropic",
        "deepseek",
        "custom",
    }
    assert HERMES_PROVIDER_SOURCE_REVISION
    ready = [entry for entry in payload if entry["enabled"]]
    assert {entry["id"] for entry in ready} >= {
        "openai",
        "openrouter",
        "deepseek",
        "xai",
    }
    assert next(entry for entry in payload if entry["id"] == "custom")["enabled"] is True
    assert all("api_key" not in entry for entry in payload)
    assert all(entry["models"] for entry in ready)
    assert all(
        entry["id"] in {provider.value for provider in _APPROVED_BASE_URLS}
        for entry in ready
    )


@pytest.mark.asyncio
async def test_ready_catalog_providers_build_routable_targets(
    provider_client: tuple[AsyncClient, EnvelopeCipher, RecordingVerifier],
    provider_session: AsyncSession,
) -> None:
    client, cipher, verifier = provider_client
    tokens = await register_owner(client)
    ready = [entry for entry in provider_catalog() if entry.enabled]
    routed = ready[:10]
    credential_ids: list[str] = []

    for index, entry in enumerate(routed):
        response = await client.post(
            "/v1/providers/credentials",
            headers=bearer(tokens),
            json={
                "provider": entry.id,
                "label": f"{entry.label} test",
                "api_key": f"sk-{entry.id}-tenant-secret-{index:04d}",
                "low_cost_model_id": entry.models[0].id,
                "strong_model_id": entry.models[1].id if len(entry.models) > 1 else None,
            },
        )
        assert response.status_code == 201
        credential_id = response.json()["id"]
        credential_ids.append(credential_id)
        verified = await client.post(
            f"/v1/providers/credentials/{credential_id}/verify",
            headers=bearer(tokens),
        )
        assert verified.status_code == 200

    updated = await client.patch(
        "/v1/providers/policy",
        headers=bearer(tokens),
        json={"mode": "tenant_only", "credential_order": credential_ids},
    )
    assert updated.status_code == 200
    targets = await build_tenant_llm_targets(
        provider_session,
        UUID((await client.get("/v1/me", headers=bearer(tokens))).json()["tenant"]["id"]),
        cipher=cipher,
    )
    assert len(targets) >= len(routed)
    assert len(verifier.seen) == len(routed)
    for target in targets:
        if isinstance(target.provider, OpenAICompatibleLLMProvider):
            await target.provider.aclose()


class RecordingVerifier:
    def __init__(self) -> None:
        self.seen: list[str] = []
        self.fail = False

    async def verify(
        self,
        *,
        provider: GenerationProvider,
        model_id: str,
        secret: SecretStr,
    ) -> None:
        del provider, model_id
        value = secret.get_secret_value()
        self.seen.append(value)
        if self.fail:
            raise ProviderError(
                ProviderErrorCategory.AUTHENTICATION,
                f"provider rejected {value}",
                provider_id="test",
            )


@pytest_asyncio.fixture
async def provider_session() -> AsyncGenerator[AsyncSession, None]:
    engine: AsyncEngine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", poolclass=StaticPool
    )
    tables = [
        cast(Table, User.__table__),
        cast(Table, Tenant.__table__),
        cast(Table, TenantMembership.__table__),
        cast(Table, RefreshToken.__table__),
        cast(Table, ProviderCredential.__table__),
        cast(Table, ProviderPolicy.__table__),
    ]
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=tables)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def provider_client(
    provider_session: AsyncSession,
) -> AsyncGenerator[tuple[AsyncClient, EnvelopeCipher, RecordingVerifier], None]:
    cipher = EnvelopeCipher(
        LocalAesGcmKeyWrapper(bytes(range(32)), key_version="test-v1")
    )
    verifier = RecordingVerifier()

    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        yield provider_session

    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_provider_envelope_cipher] = lambda: cipher
    app.dependency_overrides[get_credential_verifier] = lambda: verifier
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, cipher, verifier
    app.dependency_overrides.clear()


async def register_owner(
    client: AsyncClient,
    *,
    email: str = "owner@example.com",
    slug: str = "acme",
) -> dict[str, Any]:
    response = await register_with_otp(
        client,
        {
            "email": email,
            "password": "correct horse battery staple",
            "organization_name": slug.title(),
            "organization_slug": slug,
        },
    )
    return cast(dict[str, Any], response.json())


def bearer(tokens: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def create_credential(
    client: AsyncClient,
    tokens: dict[str, Any],
    *,
    api_key: str = RAW_KEY,
) -> dict[str, Any]:
    response = await client.post(
        "/v1/providers/credentials",
        headers=bearer(tokens),
        json={
            "provider": "openai",
            "label": "Production",
            "api_key": api_key,
            "low_cost_model_id": "gpt-4.1-mini",
            "strong_model_id": "gpt-4.1",
        },
    )
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


@pytest.mark.asyncio
async def test_encrypted_lifecycle_masks_and_immediately_revokes_routing(
    provider_client: tuple[AsyncClient, EnvelopeCipher, RecordingVerifier],
    provider_session: AsyncSession,
) -> None:
    client, cipher, verifier = provider_client
    tokens = await register_owner(client)
    me = await client.get("/v1/me", headers=bearer(tokens))
    tenant_id = UUID(me.json()["tenant"]["id"])
    created = await create_credential(client, tokens)
    credential_id = UUID(created["id"])

    assert created["masked_secret"] == "••••1234"  # noqa: S105
    assert RAW_KEY not in str(created)
    assert {"encrypted_secret", "wrapped_data_key", "fingerprint", "api_key"}.isdisjoint(
        created
    )
    stored = await provider_session.scalar(
        select(ProviderCredential).where(ProviderCredential.id == credential_id)
    )
    assert stored is not None
    assert RAW_KEY not in stored.encrypted_secret
    assert RAW_KEY not in stored.wrapped_data_key

    verified = await client.post(
        f"/v1/providers/credentials/{credential_id}/verify", headers=bearer(tokens)
    )
    policy = await client.patch(
        "/v1/providers/policy",
        headers=bearer(tokens),
        json={"mode": "tenant_only", "credential_order": [str(credential_id)]},
    )
    assert verified.status_code == 200
    assert verified.json()["status"] == "verified"
    assert verifier.seen == [RAW_KEY]
    assert policy.status_code == 200

    targets = await build_tenant_llm_targets(provider_session, tenant_id, cipher=cipher)
    assert [target.tier for target in targets] == [ModelTier.LOW_COST, ModelTier.STRONG]
    assert all(target.provider.provider_id.startswith(f"tenant:{tenant_id}:") for target in targets)
    for provider in {id(target.provider): target.provider for target in targets}.values():
        if isinstance(provider, OpenAICompatibleLLMProvider):
            await provider.aclose()

    rotated = await client.put(
        f"/v1/providers/credentials/{credential_id}/secret",
        headers=bearer(tokens),
        json={"api_key": ROTATED_KEY},
    )
    assert rotated.status_code == 200
    assert rotated.json()["status"] == "unverified"
    assert ROTATED_KEY not in rotated.text
    with pytest.raises(TenantProviderUnavailableError):
        await build_tenant_llm_targets(provider_session, tenant_id, cipher=cipher)

    reverified = await client.post(
        f"/v1/providers/credentials/{credential_id}/verify", headers=bearer(tokens)
    )
    revoked = await client.delete(
        f"/v1/providers/credentials/{credential_id}", headers=bearer(tokens)
    )
    policy_after_revoke = await client.get("/v1/providers/policy", headers=bearer(tokens))
    assert reverified.status_code == 200
    assert verifier.seen[-1] == ROTATED_KEY
    assert revoked.status_code == 204
    assert policy_after_revoke.json() == {"mode": "tenant_only", "credential_order": []}
    with pytest.raises(TenantProviderUnavailableError):
        await build_tenant_llm_targets(provider_session, tenant_id, cipher=cipher)


@pytest.mark.asyncio
async def test_provider_api_is_role_and_tenant_isolated_and_redacts_errors(
    provider_client: tuple[AsyncClient, EnvelopeCipher, RecordingVerifier],
    provider_session: AsyncSession,
) -> None:
    client, _cipher, verifier = provider_client
    first = await register_owner(client)
    created = await create_credential(client, first)
    credential_id = created["id"]
    me = await client.get("/v1/me", headers=bearer(first))
    tenant_id = UUID(me.json()["tenant"]["id"])

    duplicate = await client.post(
        "/v1/providers/credentials",
        headers=bearer(first),
        json={
            "provider": "openai",
            "label": "Duplicate",
            "api_key": RAW_KEY,
            "low_cost_model_id": "gpt-4.1-mini",
        },
    )
    too_short_key = "raw-key"
    invalid = await client.post(
        "/v1/providers/credentials",
        headers=bearer(first),
        json={
            "provider": "openai",
            "label": "Invalid",
            "api_key": too_short_key,
            "low_cost_model_id": "gpt-4.1-mini",
        },
    )
    verifier.fail = True
    failed_verify = await client.post(
        f"/v1/providers/credentials/{credential_id}/verify", headers=bearer(first)
    )
    assert duplicate.status_code == 409
    assert invalid.status_code == 422
    assert failed_verify.status_code == 422
    assert RAW_KEY not in duplicate.text + failed_verify.text
    assert too_short_key not in invalid.text

    member = await UserRepository(provider_session).create(
        email="member@example.com",
        password_hash="unused-test-hash",  # noqa: S106
    )
    await MembershipRepository(provider_session, tenant_id).create(
        user_id=member.id, role=MembershipRole.MEMBER
    )
    await provider_session.commit()
    member_token, _ = create_access_token(member.id, tenant_id)
    member_list = await client.get(
        "/v1/providers/credentials",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert member_list.status_code == 403

    second = await register_owner(client, email="second@example.com", slug="second")
    second_list = await client.get("/v1/providers/credentials", headers=bearer(second))
    cross_verify = await client.post(
        f"/v1/providers/credentials/{credential_id}/verify", headers=bearer(second)
    )
    cross_revoke = await client.delete(
        f"/v1/providers/credentials/{credential_id}", headers=bearer(second)
    )
    assert second_list.json() == []
    assert cross_verify.status_code == 404
    assert cross_revoke.status_code == 404


@pytest.mark.asyncio
async def test_explicit_platform_fallback_is_used_only_by_fallback_mode(
    provider_client: tuple[AsyncClient, EnvelopeCipher, RecordingVerifier],
    provider_session: AsyncSession,
) -> None:
    client, cipher, _verifier = provider_client
    tokens = await register_owner(client)
    me = await client.get("/v1/me", headers=bearer(tokens))
    tenant_id = UUID(me.json()["tenant"]["id"])
    created = await create_credential(client, tokens)
    credential_id = created["id"]
    await client.post(
        f"/v1/providers/credentials/{credential_id}/verify", headers=bearer(tokens)
    )
    updated = await client.patch(
        "/v1/providers/policy",
        headers=bearer(tokens),
        json={
            "mode": ProviderRoutingMode.TENANT_FIRST_WITH_PLATFORM_FALLBACK.value,
            "credential_order": [credential_id],
        },
    )
    assert updated.status_code == 200
    targets = await build_tenant_llm_targets(provider_session, tenant_id, cipher=cipher)
    assert targets[0].provider.provider_id.startswith("tenant:")
    assert any(not target.provider.provider_id.startswith("tenant:") for target in targets)
    for provider in {id(target.provider): target.provider for target in targets}.values():
        if isinstance(provider, OpenAICompatibleLLMProvider):
            await provider.aclose()

    await client.delete(
        f"/v1/providers/credentials/{credential_id}", headers=bearer(tokens)
    )
    fallback_targets = await build_tenant_llm_targets(
        provider_session, tenant_id, cipher=cipher
    )
    assert fallback_targets
    assert all(
        not target.provider.provider_id.startswith("tenant:")
        for target in fallback_targets
    )
