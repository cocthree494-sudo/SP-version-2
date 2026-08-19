"""Platform-owner authorization and mutation contract tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import cast
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from app.core.config import settings
from app.core.security import create_access_token
from app.db.base import Base
from app.domains.platform_admin.models import (
    PlatformAdmin,
    PlatformAdminAuditLog,
    PlatformAdminStatus,
)
from app.domains.platform_admin.schemas import AdminActionRequest
from app.domains.platform_admin.service import (
    PlatformAdminContext,
    admin_action_is_replay,
    audit,
    require_platform_admin,
)
from app.domains.tenancy.enums import UserStatus
from app.domains.tenancy.models import User


@pytest_asyncio.fixture
async def admin_session() -> AsyncGenerator[AsyncSession, None]:
    engine: AsyncEngine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )
    tables = [
        cast(Table, User.__table__),
        cast(Table, PlatformAdmin.__table__),
        cast(Table, PlatformAdminAuditLog.__table__),
    ]
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=tables)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def admin_request(access_token: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/v1/admin/summary",
            "headers": [(b"authorization", f"Bearer {access_token}".encode())],
            "client": ("127.0.0.1", 1234),
        }
    )


@pytest.mark.asyncio
async def test_tenant_user_is_not_implicitly_a_platform_admin(
    admin_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "PLATFORM_ADMIN_EMAILS", "")
    user = User(email="tenant-owner@example.com", status=UserStatus.ACTIVE)
    admin_session.add(user)
    await admin_session.commit()
    token, _ = create_access_token(user.id, uuid4())

    with pytest.raises(HTTPException) as denied:
        await require_platform_admin(admin_request(token), admin_session)

    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_approved_identity_bootstraps_separate_platform_access(
    admin_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "PLATFORM_ADMIN_EMAILS", " Owner@Example.com ")
    user = User(email="owner@example.com", status=UserStatus.ACTIVE)
    admin_session.add(user)
    await admin_session.commit()
    token, _ = create_access_token(user.id, uuid4())

    context = await require_platform_admin(admin_request(token), admin_session)

    assert context.user.id == user.id
    assert context.admin.status is PlatformAdminStatus.ACTIVE


@pytest.mark.asyncio
async def test_platform_admin_requires_a_recent_otp_session(
    admin_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = User(email="admin@example.com", status=UserStatus.ACTIVE)
    admin_session.add(user)
    await admin_session.flush()
    admin_session.add(PlatformAdmin(user_id=user.id, status=PlatformAdminStatus.ACTIVE))
    await admin_session.commit()
    token, _ = create_access_token(user.id, uuid4())
    monkeypatch.setattr(settings, "ADMIN_SESSION_MAX_AGE_SECONDS", -1)

    with pytest.raises(HTTPException) as denied:
        await require_platform_admin(admin_request(token), admin_session)

    assert denied.value.status_code == 401
    assert "recent OTP" in str(denied.value.detail)


@pytest.mark.asyncio
async def test_admin_idempotency_accepts_exact_replay_and_rejects_payload_reuse(
    admin_session: AsyncSession,
) -> None:
    user = User(email="admin@example.com", status=UserStatus.ACTIVE)
    admin_session.add(user)
    await admin_session.flush()
    admin = PlatformAdmin(user_id=user.id, status=PlatformAdminStatus.ACTIVE)
    admin_session.add(admin)
    await admin_session.flush()
    token, _ = create_access_token(user.id, uuid4())
    context = PlatformAdminContext(
        user=user,
        admin=admin,
        claims=(await require_platform_admin(admin_request(token), admin_session)).claims,
    )
    target_id = uuid4()
    request = admin_request(token)
    await audit(
        admin_session,
        context=context,
        request=request,
        action="admin.user.status",
        target_type="user",
        target_id=target_id,
        reason="Security response",
        change_summary={"status": "disabled", "idempotency_key": "request-123"},
    )
    await admin_session.commit()

    assert await admin_action_is_replay(
        admin_session,
        context=context,
        action="admin.user.status",
        target_type="user",
        target_id=target_id,
        idempotency_key="request-123",
        reason="Security response",
        expected_change={"status": "disabled"},
    )
    with pytest.raises(HTTPException) as conflict:
        await admin_action_is_replay(
            admin_session,
            context=context,
            action="admin.user.status",
            target_type="user",
            target_id=target_id,
            idempotency_key="request-123",
            reason="Different reason",
            expected_change={"status": "active"},
        )
    assert conflict.value.status_code == 409


def test_admin_status_contract_distinguishes_users_from_tenants() -> None:
    assert AdminActionRequest(
        status="disabled",
        reason="Security response",
        confirmation="CONFIRM",
        idempotency_key="request-123",
    ).status == "disabled"
    with pytest.raises(ValidationError):
        AdminActionRequest(
            status="revoked",  # type: ignore[arg-type]
            reason="Security response",
            confirmation="CONFIRM",
            idempotency_key="request-123",
        )
