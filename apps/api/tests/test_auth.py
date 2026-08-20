"""Authentication API, rotation, hashing, and tenant-binding tests."""

from __future__ import annotations

import asyncio
import re
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
from app.domains.auth.email import InMemoryAuthEmailSender
from app.domains.auth.models import RefreshToken
from app.domains.auth.oauth import OAuthProfile
from app.domains.auth.otp import AuthOtpExpiredError, AuthOtpService, PendingAuth
from app.domains.auth.repositories import RefreshTokenRepository
from app.domains.tenancy.models import ProviderIdentity, Tenant, TenantMembership, User
from app.domains.tenancy.repositories import UserRepository
from app.main import app
from tests.auth_helpers import (
    latest_otp,
    register_with_otp,
    verify_latest_otp,
)


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
    started = await auth_client.post("/v1/auth/register", json=registration_payload())

    assert started.status_code == 202
    assert started.json()["status"] == "otp_required"
    assert started.json()["flow"] == "register"
    assert await UserRepository(auth_session).get_by_email("owner@example.com") is None
    assert await auth_session.scalar(select(RefreshToken)) is None

    response = await verify_latest_otp(
        auth_client,
        started,
        email="owner@example.com",
    )
    assert response.status_code == 200
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
async def test_register_duplicate_identity_does_not_enumerate_before_otp(
    auth_client: AsyncClient,
    auth_session: AsyncSession,
) -> None:
    first = await register_with_otp(auth_client, registration_payload())
    duplicate = await auth_client.post(
        "/v1/auth/register",
        json=registration_payload(
            email="owner@example.com",
            organization_name="Uncommitted Tenant",
            organization_slug="uncommitted-tenant",
        ),
    )

    assert first.status_code == 200
    assert duplicate.status_code == 202
    assert duplicate.json()["status"] == "otp_required"
    duplicate_verified = await verify_latest_otp(
        auth_client,
        duplicate,
        email="owner@example.com",
    )
    assert duplicate_verified.status_code == 409
    tenants = list(await auth_session.scalars(select(Tenant).order_by(Tenant.created_at)))
    assert [tenant.slug for tenant in tenants] == ["acme-support"]


@pytest.mark.asyncio
async def test_login_uses_generic_failure_and_accepts_normalized_email(
    auth_client: AsyncClient,
) -> None:
    await register_with_otp(auth_client, registration_payload())

    bad_response = await auth_client.post(
        "/v1/auth/login",
        json={"email": "missing@example.com", "password": "wrong-password"},
    )
    good_start = await auth_client.post(
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
    assert good_start.status_code == 200
    assert "access_token" not in good_start.json()
    assert good_start.json()["flow"] == "login"
    good_response = await verify_latest_otp(
        auth_client,
        good_start,
        email="owner@example.com",
    )
    assert good_response.status_code == 200
    assert good_response.json()["access_token"]


@pytest.mark.asyncio
async def test_otp_is_single_use_and_wrong_codes_never_create_a_session(
    auth_client: AsyncClient,
    auth_session: AsyncSession,
) -> None:
    started = await auth_client.post("/v1/auth/register", json=registration_payload())
    challenge_id = started.json()["challenge_id"]
    code = latest_otp("owner@example.com")

    wrong = await auth_client.post(
        "/v1/auth/otp/verify",
        json={
            "challenge_id": challenge_id,
            "code": "Z9x8C7v6" if code != "Z9x8C7v6" else "Q2w3E4r5",
        },
    )
    assert wrong.status_code == 400
    assert await UserRepository(auth_session).get_by_email("owner@example.com") is None

    verified = await auth_client.post(
        "/v1/auth/otp/verify",
        json={"challenge_id": challenge_id, "code": code},
    )
    assert verified.status_code == 200
    replayed = await auth_client.post(
        "/v1/auth/otp/verify",
        json={"challenge_id": challenge_id, "code": code},
    )
    assert replayed.status_code == 410


def test_generated_otp_codes_are_eight_character_mixed_alphanumeric(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "AUTH_OTP_TEST_CODE", None)
    codes = {AuthOtpService._new_code() for _ in range(32)}

    assert len(codes) == 32
    assert all(
        re.fullmatch(r"(?=.*[A-Za-z])(?=.*[0-9])[A-Za-z0-9]{8}", code)
        for code in codes
    )


@pytest.mark.asyncio
async def test_admin_flow_is_google_only_and_uses_fixed_otp_mailbox(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.domains.auth.service as auth_service
    from app.core.config import settings

    headers = {"X-Relay-Admin-Flow": "1"}
    password_login = await auth_client.post(
        "/v1/auth/login",
        headers=headers,
        json={"email": "owner@example.com", "password": "not-used"},
    )
    microsoft = await auth_client.post(
        "/v1/auth/oauth/microsoft/start",
        headers=headers,
        json={"mode": "login"},
    )
    assert password_login.status_code == 404
    assert microsoft.status_code == 404

    monkeypatch.setattr(settings, "OAUTH_GOOGLE_CLIENT_ID", "google-client")
    monkeypatch.setattr(settings, "OAUTH_GOOGLE_CLIENT_SECRET", SecretStr("google-secret"))
    monkeypatch.setattr(settings, "OAUTH_ADMIN_WEB_BASE_URL", "https://admin.example.com")
    google = await auth_client.post(
        "/v1/auth/oauth/google/start",
        headers=headers,
        json={"mode": "login"},
    )
    assert google.status_code == 200
    assert (
        "redirect_uri=https%3A%2F%2Fadmin.example.com%2Fapi%2Fauth%2Foauth%2Fgoogle%2Fcallback"
        in google.json()["authorization_url"]
    )

    async def fake_exchange(provider: str, *, code: str, oauth_state: object) -> OAuthProfile:
        assert provider == "google"
        assert code == "admin-provider-code"
        return OAuthProfile(
            provider="google",
            issuer="https://accounts.google.com",
            subject="new-admin-google-subject",
            email="signed-in-google-account@example.com",
            email_verified=True,
            display_name="Platform Operator",
        )

    monkeypatch.setattr(auth_service, "exchange_code", fake_exchange)
    from urllib.parse import parse_qs, urlparse

    state = parse_qs(urlparse(google.json()["authorization_url"]).query)["state"][0]
    callback = await auth_client.post(
        "/v1/auth/oauth/google/callback",
        headers=headers,
        json={"code": "admin-provider-code", "state": state},
    )
    assert callback.status_code == 200
    assert callback.json()["status"] == "otp_required"
    assert callback.json()["flow"] == "register"
    assert callback.json()["continuation_token"] is None
    assert app.state.auth_email_sender.deliveries[-1].email == settings.platform_admin_otp_email
    assert callback.json()["email_hint"].endswith("@gmail.com")


@pytest.mark.asyncio
async def test_otp_attempt_exhaustion_locks_the_challenge(
    auth_client: AsyncClient,
) -> None:
    started = await auth_client.post("/v1/auth/register", json=registration_payload())
    challenge_id = started.json()["challenge_id"]
    code = latest_otp("owner@example.com")
    wrong_code = "Z9x8C7v6" if code != "Z9x8C7v6" else "Q2w3E4r5"

    for _ in range(4):
        wrong = await auth_client.post(
            "/v1/auth/otp/verify",
            json={"challenge_id": challenge_id, "code": wrong_code},
        )
        assert wrong.status_code == 400
    locked = await auth_client.post(
        "/v1/auth/otp/verify",
        json={"challenge_id": challenge_id, "code": wrong_code},
    )
    assert locked.status_code == 429
    assert (
        await auth_client.post(
            "/v1/auth/otp/verify",
            json={"challenge_id": challenge_id, "code": code},
        )
    ).status_code == 410


@pytest.mark.asyncio
async def test_otp_verification_is_atomic_under_concurrent_requests(
    auth_client: AsyncClient,
) -> None:
    del auth_client
    from app.core.config import settings

    service = AuthOtpService(app.state.auth_otp_store, app.state.auth_email_sender)
    challenge = await service.start(
        PendingAuth(kind="password_login", email="owner@example.com", payload={}),
        client_ip="127.0.0.1",
    )
    code = latest_otp("owner@example.com")
    outcomes = await asyncio.gather(
        service.verify(challenge.challenge_id, code),
        service.verify(challenge.challenge_id, code),
        return_exceptions=True,
    )
    assert sum(isinstance(item, PendingAuth) for item in outcomes) == 1
    assert sum(isinstance(item, AuthOtpExpiredError) for item in outcomes) == 1
    assert settings.AUTH_OTP_MAX_ATTEMPTS >= 3


@pytest.mark.asyncio
async def test_otp_redis_failure_returns_secret_safe_unavailable_response(
    auth_client: AsyncClient,
) -> None:
    class BrokenOtpStore:
        async def allow_rate(self, *_args: object) -> bool:
            raise RuntimeError("redis is offline")

    app.state.auth_otp_store = BrokenOtpStore()
    response = await auth_client.post("/v1/auth/register", json=registration_payload())
    assert response.status_code == 503
    assert "redis is offline" not in response.text


@pytest.mark.asyncio
async def test_otp_email_failure_removes_challenge_and_leaks_no_provider_error(
    auth_client: AsyncClient,
    auth_session: AsyncSession,
) -> None:
    from app.domains.auth.email import AuthEmailDeliveryError

    class BrokenEmailSender:
        async def send_otp(self, **_kwargs: object) -> None:
            raise AuthEmailDeliveryError("smtp account detail")

    app.state.auth_email_sender = BrokenEmailSender()
    response = await auth_client.post("/v1/auth/register", json=registration_payload())
    assert response.status_code == 503
    assert "smtp account detail" not in response.text
    assert await UserRepository(auth_session).get_by_email("owner@example.com") is None


@pytest.mark.asyncio
async def test_otp_request_rate_limit_is_enforced_per_email(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "AUTH_OTP_EMAIL_RATE_LIMIT", 1)
    first = await auth_client.post("/v1/auth/register", json=registration_payload())
    limited = await auth_client.post("/v1/auth/register", json=registration_payload())
    assert first.status_code == 202
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) > 0


@pytest.mark.asyncio
async def test_expired_otp_never_creates_registration(
    auth_client: AsyncClient,
    auth_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.domains.auth.otp as otp_module
    from app.core.config import settings

    started = await auth_client.post("/v1/auth/register", json=registration_payload())
    challenge_id = started.json()["challenge_id"]
    code = latest_otp("owner@example.com")
    current_time = otp_module.time.time()
    monkeypatch.setattr(
        otp_module.time,
        "time",
        lambda: current_time + settings.AUTH_OTP_TTL_SECONDS + 1,
    )
    expired = await auth_client.post(
        "/v1/auth/otp/verify",
        json={"challenge_id": challenge_id, "code": code},
    )
    assert expired.status_code == 410
    assert await UserRepository(auth_session).get_by_email("owner@example.com") is None


def test_test_only_otp_code_is_rejected_outside_test_environment() -> None:
    from app.core.config import Settings

    with pytest.raises(ValueError, match="AUTH_OTP_TEST_CODE"):
        Settings(
            APP_ENV="production",
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
            REDIS_URL="redis://127.0.0.1:6379/15",
            AUTH_JWT_SECRET=SecretStr("a" * 40),
            AUTH_OTP_SECRET=SecretStr("b" * 40),
            AUTH_OTP_TEST_CODE=SecretStr("A1b2C3d4"),
        )


@pytest.mark.asyncio
async def test_otp_cancel_removes_pending_registration(
    auth_client: AsyncClient,
    auth_session: AsyncSession,
) -> None:
    started = await auth_client.post("/v1/auth/register", json=registration_payload())
    challenge_id = started.json()["challenge_id"]

    cancelled = await auth_client.post(
        "/v1/auth/otp/cancel",
        json={"challenge_id": challenge_id},
    )
    assert cancelled.status_code == 204

    expired = await auth_client.post(
        "/v1/auth/otp/verify",
        json={"challenge_id": challenge_id, "code": latest_otp("owner@example.com")},
    )
    assert expired.status_code == 410
    assert await UserRepository(auth_session).get_by_email("owner@example.com") is None


@pytest.mark.asyncio
async def test_resend_replaces_the_previous_code(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "AUTH_OTP_RESEND_COOLDOWN_SECONDS", 0)
    started = await auth_client.post("/v1/auth/register", json=registration_payload())
    challenge_id = started.json()["challenge_id"]
    original_code = latest_otp("owner@example.com")

    resent = await auth_client.post(
        "/v1/auth/otp/resend",
        json={"challenge_id": challenge_id},
    )
    assert resent.status_code == 200
    replacement_code = latest_otp("owner@example.com")
    assert replacement_code != original_code

    old_code = await auth_client.post(
        "/v1/auth/otp/verify",
        json={"challenge_id": challenge_id, "code": original_code},
    )
    assert old_code.status_code == 400
    replacement = await auth_client.post(
        "/v1/auth/otp/verify",
        json={"challenge_id": challenge_id, "code": replacement_code},
    )
    assert replacement.status_code == 200


@pytest.mark.asyncio
async def test_refresh_rotation_rejects_reuse_and_revokes_family(
    auth_client: AsyncClient,
) -> None:
    register_response = await register_with_otp(auth_client, registration_payload())
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
    first_response = await register_with_otp(auth_client, registration_payload())
    second_response = await register_with_otp(
        auth_client,
        registration_payload(
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

    complete_start = await auth_client.post(
        "/v1/auth/oauth/register",
        json={
            "continuation_token": callback_data["continuation_token"],
            "organization_name": "Social Workspace",
        },
    )
    assert complete_start.status_code == 200
    assert complete_start.json()["status"] == "otp_required"
    assert complete_start.json()["flow"] == "register"
    assert await UserRepository(auth_session).get_by_email("social@example.com") is None
    complete = await verify_latest_otp(
        auth_client,
        complete_start,
        email="social@example.com",
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

    sender = cast(InMemoryAuthEmailSender, app.state.auth_email_sender)
    deliveries_before_duplicate = len(sender.deliveries)
    duplicate_register_start = await auth_client.post(
        "/v1/auth/oauth/google/start",
        json={"mode": "register"},
    )
    duplicate_register_state = parse_qs(
        urlparse(duplicate_register_start.json()["authorization_url"]).query
    )["state"][0]
    duplicate_register_callback = await auth_client.post(
        "/v1/auth/oauth/google/callback",
        json={"code": "provider-code", "state": duplicate_register_state},
    )
    assert duplicate_register_callback.status_code == 409
    assert duplicate_register_callback.json()["detail"] == (
        "This social account already has a Relay account. Sign in instead."
    )
    assert len(sender.deliveries) == deliveries_before_duplicate

    login_start = await auth_client.post(
        "/v1/auth/oauth/google/start",
        json={"mode": "login"},
    )
    login_state = parse_qs(urlparse(login_start.json()["authorization_url"]).query)["state"][0]
    login_callback = await auth_client.post(
        "/v1/auth/oauth/google/callback",
        json={"code": "provider-code", "state": login_state},
    )
    assert login_callback.status_code == 200
    assert login_callback.json()["status"] == "otp_required"
    assert login_callback.json()["flow"] == "login"
    assert "access_token" not in login_callback.json()
    login_complete = await verify_latest_otp(
        auth_client,
        login_callback,
        email="social@example.com",
    )
    assert login_complete.status_code == 200


@pytest.mark.asyncio
async def test_account_deletion_requires_typed_confirmation_and_releases_email(
    auth_client: AsyncClient,
    auth_session: AsyncSession,
) -> None:
    registered = await register_with_otp(auth_client, registration_payload())
    token = registered.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    rejected = await auth_client.post(
        "/v1/account/delete",
        headers=headers,
        json={"password": "correct horse battery staple", "confirmation": "DELETE"},
    )
    assert rejected.status_code == 422
    deleted = await auth_client.post(
        "/v1/account/delete",
        headers=headers,
        json={"password": "correct horse battery staple", "confirmation": "DELETE MY ACCOUNT"},
    )
    assert deleted.status_code == 204
    assert await UserRepository(auth_session).get_by_email("owner@example.com") is None
    reused = await register_with_otp(
        auth_client,
        registration_payload(email="owner@example.com", organization_name="Reused"),
    )
    assert reused.status_code == 200
