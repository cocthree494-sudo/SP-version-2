"""Authorization, redacted reporting, and audited platform mutations."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import HTTPException, Request, status
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import AccessTokenClaims, AccessTokenError, decode_access_token
from app.domains.auth.models import RefreshToken
from app.domains.platform_admin.models import (
    PlatformAdmin,
    PlatformAdminAuditLog,
    PlatformAdminStatus,
)
from app.domains.tenancy.enums import UserStatus
from app.domains.tenancy.models import User


class PlatformAdminContext:
    def __init__(self, *, user: User, admin: PlatformAdmin, claims: AccessTokenClaims) -> None:
        self.user = user
        self.admin = admin
        self.claims = claims


async def require_platform_admin(
    request: Request,
    session: AsyncSession,
) -> PlatformAdminContext:
    """Fail closed unless a recent OTP-issued access token belongs to an admin."""

    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.casefold() != "bearer" or not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin authentication required")
    try:
        claims = decode_access_token(token)
    except AccessTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin authentication required") from None
    if not claims.otp_verified or datetime.now(UTC) - claims.issued_at > timedelta(seconds=settings.ADMIN_SESSION_MAX_AGE_SECONDS):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="A recent OTP verification is required")

    user = await session.scalar(select(User).where(User.id == claims.user_id))
    if user is None or user.status is not UserStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Platform admin access denied")
    admin = await session.scalar(select(PlatformAdmin).where(PlatformAdmin.user_id == user.id))
    if admin is None and user.email in settings.platform_admin_emails:
        admin = PlatformAdmin(user_id=user.id, status=PlatformAdminStatus.ACTIVE, granted_by_user_id=user.id)
        session.add(admin)
        await session.flush()
    if admin is None or admin.status is not PlatformAdminStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Platform admin access denied")
    return PlatformAdminContext(user=user, admin=admin, claims=claims)


def admin_page(page: int, page_size: int, total: int) -> dict[str, int]:
    return {"page": page, "page_size": page_size, "total": total, "pages": max(1, math.ceil(total / page_size))}


def _safe_page(page: int, page_size: int) -> tuple[int, int]:
    return max(1, min(page, 10_000)), max(1, min(page_size, 100))


async def audit(
    session: AsyncSession,
    *,
    context: PlatformAdminContext,
    request: Request,
    action: str,
    target_type: str,
    target_id: UUID | None = None,
    outcome: str = "success",
    reason: str | None = None,
    change_summary: dict[str, Any] | None = None,
) -> None:
    session.add(
        PlatformAdminAuditLog(
            actor_user_id=context.user.id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            reason=reason,
            outcome=outcome,
            request_id=request.headers.get("x-request-id"),
            ip_address=(request.client.host if request.client else None),
            user_agent=request.headers.get("user-agent", "")[:512] or None,
            change_summary=change_summary or {},
        )
    )


async def report_rows(
    session: AsyncSession,
    *,
    view: str,
    columns: tuple[str, ...],
    where: str = "TRUE",
    params: dict[str, Any] | None = None,
    order_by: str = "created_at DESC",
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[dict[str, Any]], int]:
    """Query only caller-owned constant view/column fragments. Values stay bound."""

    allowed_views = {
        "platform_admin_audit_log",
        "platform_admin_channel_health",
        "platform_admin_ingestion_jobs",
        "platform_admin_provider_health",
        "platform_admin_tenant_directory",
        "platform_admin_usage_events",
        "platform_admin_user_directory",
        "platform_admin_voice_health",
    }
    if view not in allowed_views:
        raise ValueError("Unknown reporting view")
    if any(not value.replace("_", "").isalnum() for value in columns):
        raise ValueError("Invalid reporting column")
    page, page_size = _safe_page(page, page_size)
    values = dict(params or {})
    count_query = f"SELECT COUNT(*) FROM {view} WHERE {where}"  # noqa: S608
    total = int(await session.scalar(text(count_query), values) or 0)
    page_query = (  # noqa: S608
        f"SELECT {', '.join(columns)} FROM {view} WHERE {where} "
        f"ORDER BY {order_by} LIMIT :limit OFFSET :offset"
    )
    result = await session.execute(
        text(page_query),
        {**values, "limit": page_size, "offset": (page - 1) * page_size},
    )
    return [dict(row) for row in result.mappings().all()], total


async def report_scalar(session: AsyncSession, query: str, params: dict[str, Any] | None = None) -> Any:
    return await session.scalar(text(query), params or {})


async def revoke_user_sessions(session: AsyncSession, reporting: AsyncSession, user_id: UUID) -> int:
    tenant_rows = await reporting.execute(
        text("SELECT DISTINCT tenant_id FROM platform_admin_session_health WHERE user_id = :user_id"),
        {"user_id": user_id},
    )
    now = datetime.now(UTC)
    count = 0
    for row in tenant_rows.mappings():
        tenant_id = row["tenant_id"]
        await session.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": str(tenant_id)},
        ) if session.get_bind().dialect.name == "postgresql" else None
        result = await session.execute(
            update(RefreshToken).where(RefreshToken.tenant_id == tenant_id, RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)).values(revoked_at=now)
        )
        count += result.rowcount or 0
    return count


__all__ = [
    "PlatformAdminContext",
    "admin_page",
    "audit",
    "report_rows",
    "report_scalar",
    "require_platform_admin",
    "revoke_user_sessions",
]
