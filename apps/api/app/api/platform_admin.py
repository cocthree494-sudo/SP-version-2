"""Protected platform-admin reporting and lifecycle endpoints."""

# Reporting SQL is assembled only from internal constants and allow-listed filters.
# ruff: noqa: E501, S608

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.reporting import get_reporting_session
from app.db.session import get_db_session
from app.domains.platform_admin.models import PlatformAdmin, PlatformAdminStatus
from app.domains.platform_admin.schemas import (
    AdminActionRequest,
    AdminAuditListResponse,
    AdminAuditRow,
    AdminDirectoryRow,
    AdminGrantRequest,
    AdminHealthListResponse,
    AdminHealthRow,
    AdminIngestionListResponse,
    AdminIngestionRow,
    AdminPage,
    AdminRevokeSessionsRequest,
    AdminSummaryResponse,
    AdminTenantListResponse,
    AdminTenantRow,
    AdminUsageListResponse,
    AdminUsageRow,
    AdminUserListResponse,
    AdminUserRow,
)
from app.domains.platform_admin.service import (
    PlatformAdminContext,
    admin_action_is_replay,
    admin_page,
    audit,
    commit_admin_action,
    report_rows,
    report_scalar,
    require_platform_admin,
    revoke_user_sessions,
)
from app.domains.tenancy.enums import TenantStatus, UserStatus
from app.domains.tenancy.models import Tenant, User

router = APIRouter(prefix="/v1/admin", tags=["platform-admin"])
DbSession = Annotated[AsyncSession, Depends(get_db_session)]
ReportSession = Annotated[AsyncSession, Depends(get_reporting_session)]


async def admin_context(request: Request, session: DbSession) -> PlatformAdminContext:
    return await require_platform_admin(request, session)


CurrentAdmin = Annotated[PlatformAdminContext, Depends(admin_context)]


def _page_model(page: int, page_size: int, total: int) -> AdminPage:
    return AdminPage(**admin_page(page, page_size, total))


async def _read_audit(
    session: AsyncSession,
    context: PlatformAdminContext,
    request: Request,
    action: str,
    target_type: str,
    target_id: UUID | None = None,
) -> None:
    await audit(
        session,
        context=context,
        request=request,
        action=action,
        target_type=target_type,
        target_id=target_id,
        change_summary={"read_only": True},
    )
    await session.commit()


@router.get("/summary", response_model=AdminSummaryResponse)
async def summary(
    request: Request,
    session: DbSession,
    reporting: ReportSession,
    context: CurrentAdmin,
    start: Annotated[datetime | None, Query()] = None,
    end: Annotated[datetime | None, Query()] = None,
) -> AdminSummaryResponse:
    if start and start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if end and end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    usage_where = "TRUE"
    usage_params: dict[str, Any] = {}
    if start:
        usage_where += " AND created_at >= :start"
        usage_params["start"] = start
    if end:
        usage_where += " AND created_at < :end"
        usage_params["end"] = end
    users_total = int(await report_scalar(reporting, "SELECT COUNT(*) FROM platform_admin_user_directory") or 0)
    users_active = int(await report_scalar(reporting, "SELECT COUNT(*) FROM platform_admin_user_directory WHERE status = 'active'") or 0)
    tenants_total = int(await report_scalar(reporting, "SELECT COUNT(*) FROM platform_admin_tenant_directory") or 0)
    tenants_active = int(await report_scalar(reporting, "SELECT COUNT(*) FROM platform_admin_tenant_directory WHERE status = 'active'") or 0)
    bots = int(await report_scalar(reporting, "SELECT COALESCE(SUM(bot_count), 0) FROM platform_admin_tenant_directory") or 0)
    conversations = int(await report_scalar(reporting, "SELECT COALESCE(SUM(conversation_count), 0) FROM platform_admin_tenant_directory") or 0)
    usage = await reporting.execute(
        text(
            "SELECT COUNT(*)::int AS requests, COALESCE(SUM(input_tokens + output_tokens), 0)::bigint AS tokens, "
            "COALESCE(SUM(estimated_cost_microusd), 0)::bigint AS cost, "
            "COALESCE(AVG(latency_ms), 0)::float AS latency FROM platform_admin_usage_events WHERE "
            + usage_where
        ),
        usage_params,
    )
    usage_row = dict(usage.mappings().one())
    ingestion_result = await reporting.execute(text("SELECT state, COUNT(*)::int AS count FROM platform_admin_ingestion_jobs GROUP BY state"))
    ingestion = {str(row["state"]): int(row["count"]) for row in ingestion_result.mappings()}
    channel_result = await reporting.execute(text("SELECT status, COUNT(*)::int AS count FROM platform_admin_channel_health GROUP BY status"))
    channels = {str(row["status"]): int(row["count"]) for row in channel_result.mappings()}
    voice_result = await reporting.execute(text("SELECT status, COUNT(*)::int AS count FROM platform_admin_voice_health GROUP BY status"))
    voice = {str(row["status"]): int(row["count"]) for row in voice_result.mappings()}
    trend_result = await reporting.execute(
        text(
            "SELECT date_trunc('day', created_at) AS day, COUNT(*)::int AS requests, "
            "COALESCE(SUM(input_tokens + output_tokens), 0)::bigint AS tokens, "
            "COALESCE(SUM(estimated_cost_microusd), 0)::bigint AS cost "
            "FROM platform_admin_usage_events WHERE " + usage_where + " GROUP BY 1 ORDER BY 1"
        ),
        usage_params,
    )
    trend = [dict(row) for row in trend_result.mappings()]
    await _read_audit(session, context, request, "admin.summary.read", "platform")
    return AdminSummaryResponse(
        generated_at=datetime.now(UTC),
        range_start=start,
        range_end=end,
        users={"total": users_total, "active": users_active, "disabled": users_total - users_active},
        tenants={"total": tenants_total, "active": tenants_active, "suspended": tenants_total - tenants_active},
        bots=bots,
        conversations=conversations,
        usage={"requests": int(usage_row["requests"]), "tokens": int(usage_row["tokens"]), "cost_microusd": int(usage_row["cost"]), "average_latency_ms": int(float(usage_row["latency"]))},
        ingestion=ingestion,
        channels=channels,
        voice=voice,
        security={
            "otp_email_provider": (
                "configured" if settings.AUTH_EMAIL_PROVIDER == "smtp" else "unavailable"
            ),
            "active_sessions": int(
                await report_scalar(
                    reporting,
                    "SELECT COALESCE(SUM(active_session_count), 0) "
                    "FROM platform_admin_user_directory",
                )
                or 0
            ),
        },
        readiness={"api": "ready", "reporting": "ready"},
        usage_trend=trend,
    )


@router.get("/tenants", response_model=AdminTenantListResponse)
async def tenants(
    request: Request,
    session: DbSession,
    reporting: ReportSession,
    context: CurrentAdmin,
    q: str | None = Query(default=None, max_length=200),
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> AdminTenantListResponse:
    where = "TRUE"
    params: dict[str, Any] = {}
    if q:
        where += " AND (name ILIKE :q OR slug ILIKE :q)"
        params["q"] = f"%{q.strip()}%"
    if status_filter in {"active", "suspended"}:
        where += " AND status = :status"
        params["status"] = status_filter
    rows, total = await report_rows(reporting, view="platform_admin_tenant_directory", columns=("tenant_id", "name", "slug", "status", "created_at", "member_count", "bot_count", "source_count", "conversation_count", "token_count", "estimated_cost_microusd", "last_activity_at"), where=where, params=params, page=page, page_size=page_size)
    await _read_audit(session, context, request, "admin.tenants.read", "tenant")
    return AdminTenantListResponse(items=[AdminTenantRow(**row) for row in rows], page=_page_model(page, page_size, total))


@router.get("/users", response_model=AdminUserListResponse)
async def users(
    request: Request,
    session: DbSession,
    reporting: ReportSession,
    context: CurrentAdmin,
    q: str | None = Query(default=None, max_length=200),
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> AdminUserListResponse:
    where = "TRUE"
    params: dict[str, Any] = {}
    if q:
        where += " AND (email ILIKE :q OR COALESCE(display_name, '') ILIKE :q)"
        params["q"] = f"%{q.strip()}%"
    if status_filter in {"active", "disabled"}:
        where += " AND status = :status"
        params["status"] = status_filter
    rows, total = await report_rows(reporting, view="platform_admin_user_directory", columns=("user_id", "email", "display_name", "status", "email_verified_at", "created_at", "tenant_count", "last_session_at", "active_session_count"), where=where, params=params, page=page, page_size=page_size)
    await _read_audit(session, context, request, "admin.users.read", "user")
    return AdminUserListResponse(items=[AdminUserRow(**row) for row in rows], page=_page_model(page, page_size, total))


@router.get("/usage", response_model=AdminUsageListResponse)
async def usage(
    request: Request,
    session: DbSession,
    reporting: ReportSession,
    context: CurrentAdmin,
    q: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> AdminUsageListResponse:
    where = "TRUE"
    params: dict[str, Any] = {}
    if q:
        where += " AND (tenant_name ILIKE :q OR provider ILIKE :q OR model ILIKE :q)"
        params["q"] = f"%{q.strip()}%"
    rows, total = await report_rows(reporting, view="platform_admin_usage_events", columns=("usage_event_id", "tenant_id", "tenant_name", "tenant_slug", "bot_id", "operation", "provider", "model", "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "latency_ms", "estimated_cost_microusd", "created_at"), where=where, params=params, page=page, page_size=page_size)
    await _read_audit(session, context, request, "admin.usage.read", "usage")
    return AdminUsageListResponse(items=[AdminUsageRow(**row) for row in rows], page=_page_model(page, page_size, total))


@router.get("/ingestion", response_model=AdminIngestionListResponse)
async def ingestion(
    request: Request,
    session: DbSession,
    reporting: ReportSession,
    context: CurrentAdmin,
    state: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> AdminIngestionListResponse:
    where = "TRUE"
    params: dict[str, Any] = {}
    if state:
        where += " AND state = :state"
        params["state"] = state
    rows, total = await report_rows(reporting, view="platform_admin_ingestion_jobs", columns=("job_id", "tenant_id", "tenant_name", "source_id", "source_name", "job_type", "state", "attempts", "max_attempts", "progress_percent", "scheduled_at", "started_at", "completed_at", "error_code", "error_message", "created_at"), where=where, params=params, page=page, page_size=page_size)
    await _read_audit(session, context, request, "admin.ingestion.read", "ingestion")
    return AdminIngestionListResponse(items=[AdminIngestionRow(**row) for row in rows], page=_page_model(page, page_size, total))


@router.get("/health", response_model=AdminHealthListResponse)
async def health(
    request: Request,
    session: DbSession,
    reporting: ReportSession,
    context: CurrentAdmin,
    category: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> AdminHealthListResponse:
    items: list[AdminHealthRow] = []
    if category in (None, "channel"):
        rows, _ = await report_rows(reporting, view="platform_admin_channel_health", columns=("installation_id", "tenant_id", "tenant_name", "channel_type", "status", "masked_external_identity", "expires_at", "updated_at"), order_by="updated_at DESC", page=1, page_size=100)
        items.extend(AdminHealthRow(category="channel", resource_id=row["installation_id"], tenant_id=row["tenant_id"], tenant_name=row["tenant_name"], name=row["channel_type"], status=row["status"], detail={"identity": row["masked_external_identity"], "expires_at": row["expires_at"]}, updated_at=row["updated_at"]) for row in rows)
    if category in (None, "voice"):
        rows, _ = await report_rows(reporting, view="platform_admin_voice_health", columns=("installation_id", "tenant_id", "tenant_name", "provider", "masked_phone_number", "status", "outbound_enabled", "recording_enabled", "monthly_cost_limit_usd", "updated_at"), order_by="updated_at DESC", page=1, page_size=100)
        items.extend(AdminHealthRow(category="voice", resource_id=row["installation_id"], tenant_id=row["tenant_id"], tenant_name=row["tenant_name"], name=row["provider"], status=row["status"], detail={"phone_number": row["masked_phone_number"], "outbound_enabled": row["outbound_enabled"], "recording_enabled": row["recording_enabled"], "monthly_cost_limit_usd": row["monthly_cost_limit_usd"]}, updated_at=row["updated_at"]) for row in rows)
    if category in (None, "provider"):
        rows, _ = await report_rows(reporting, view="platform_admin_provider_health", columns=("credential_id", "tenant_id", "tenant_name", "provider", "label", "masked_secret", "low_cost_model_id", "strong_model_id", "status", "verified_at", "rotated_at", "revoked_at", "created_at", "routing_mode"), page=1, page_size=100)
        items.extend(AdminHealthRow(category="provider", resource_id=row["credential_id"], tenant_id=row["tenant_id"], tenant_name=row["tenant_name"], name=row["provider"], status=row["status"], detail={"label": row["label"], "masked_secret": row["masked_secret"], "low_cost_model_id": row["low_cost_model_id"], "strong_model_id": row["strong_model_id"], "verified_at": row["verified_at"], "rotated_at": row["rotated_at"], "routing_mode": row["routing_mode"]}, updated_at=row["created_at"]) for row in rows)
    total = len(items)
    start_index = (page - 1) * page_size
    await _read_audit(session, context, request, "admin.health.read", "health")
    return AdminHealthListResponse(items=items[start_index : start_index + page_size], page=_page_model(page, page_size, total))


@router.get("/audit", response_model=AdminAuditListResponse)
async def audit_log(
    request: Request,
    session: DbSession,
    reporting: ReportSession,
    context: CurrentAdmin,
    q: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> AdminAuditListResponse:
    where = "TRUE"
    params: dict[str, Any] = {}
    if q:
        where += " AND (action ILIKE :q OR target_type ILIKE :q OR outcome ILIKE :q)"
        params["q"] = f"%{q.strip()}%"
    rows, total = await report_rows(reporting, view="platform_admin_audit_log", columns=("id", "created_at", "actor_user_id", "action", "target_type", "target_id", "reason", "outcome", "request_id", "ip_address", "user_agent", "change_summary"), where=where, params=params, page=page, page_size=page_size)
    await _read_audit(session, context, request, "admin.audit.read", "audit")
    return AdminAuditListResponse(
        items=[AdminAuditRow(**row) for row in rows],
        page=_page_model(page, page_size, total),
    )


async def _status_mutation(
    *,
    request: Request,
    session: AsyncSession,
    context: PlatformAdminContext,
    target: Tenant | User,
    desired: str,
    payload: AdminActionRequest,
    target_type: str,
) -> None:
    if payload.confirmation != "CONFIRM":
        raise HTTPException(status_code=422, detail="Explicit confirmation is required")
    action = f"admin.{target_type}.status"
    if await admin_action_is_replay(
        session,
        context=context,
        action=action,
        target_type=target_type,
        target_id=target.id,
        idempotency_key=payload.idempotency_key,
        reason=payload.reason,
        expected_change={"status": desired},
    ):
        return
    if isinstance(target, Tenant):
        if desired not in {"active", "suspended"}:
            raise HTTPException(status_code=422, detail="Invalid tenant status")
        target.status = TenantStatus(desired)
    else:
        if desired not in {"active", "disabled"}:
            raise HTTPException(status_code=422, detail="Invalid user status")
        if target.id == context.user.id and desired == "disabled":
            raise HTTPException(status_code=422, detail="You cannot disable your own platform identity")
        target.status = UserStatus(desired)
    await audit(session, context=context, request=request, action=action, target_type=target_type, target_id=target.id, reason=payload.reason, change_summary={"status": desired, "idempotency_key": payload.idempotency_key})
    await commit_admin_action(session, context=context, action=action, target_type=target_type, target_id=target.id, idempotency_key=payload.idempotency_key, reason=payload.reason, expected_change={"status": desired})


@router.post("/tenants/{tenant_id}/status", status_code=status.HTTP_204_NO_CONTENT)
async def update_tenant_status(tenant_id: UUID, payload: AdminActionRequest, request: Request, session: DbSession, context: CurrentAdmin) -> None:
    tenant = await session.scalar(select(Tenant).where(Tenant.id == tenant_id))
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    await _status_mutation(request=request, session=session, context=context, target=tenant, desired=payload.status, payload=payload, target_type="tenant")


@router.post("/users/{user_id}/status", status_code=status.HTTP_204_NO_CONTENT)
async def update_user_status(user_id: UUID, payload: AdminActionRequest, request: Request, session: DbSession, context: CurrentAdmin) -> None:
    user = await session.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    await _status_mutation(request=request, session=session, context=context, target=user, desired=payload.status, payload=payload, target_type="user")


@router.post("/users/{user_id}/revoke-sessions", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_sessions(user_id: UUID, payload: AdminRevokeSessionsRequest, request: Request, session: DbSession, reporting: ReportSession, context: CurrentAdmin) -> None:
    user = await session.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    action = "admin.user.sessions.revoke"
    if await admin_action_is_replay(session, context=context, action=action, target_type="user", target_id=user_id, idempotency_key=payload.idempotency_key, reason=payload.reason):
        return
    count = await revoke_user_sessions(session, reporting, user_id)
    await audit(session, context=context, request=request, action=action, target_type="user", target_id=user_id, reason=payload.reason, change_summary={"revoked_count": count, "idempotency_key": payload.idempotency_key})
    await commit_admin_action(session, context=context, action=action, target_type="user", target_id=user_id, idempotency_key=payload.idempotency_key, reason=payload.reason)


@router.get("/admins", response_model=list[AdminDirectoryRow])
async def admins(request: Request, session: DbSession, context: CurrentAdmin) -> list[AdminDirectoryRow]:
    rows = await session.execute(select(PlatformAdmin, User).join(User, User.id == PlatformAdmin.user_id).order_by(PlatformAdmin.created_at))
    await _read_audit(session, context, request, "admin.admins.read", "platform_admin")
    return [AdminDirectoryRow(user_id=user.id, email=user.email, display_name=user.display_name, status=admin.status.value, granted_at=admin.granted_at) for admin, user in rows]


@router.post("/admins/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def grant_admin(user_id: UUID, payload: AdminGrantRequest, request: Request, session: DbSession, context: CurrentAdmin) -> None:
    user = await session.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    action = "admin.platform_admin.grant"
    if await admin_action_is_replay(session, context=context, action=action, target_type="user", target_id=user_id, idempotency_key=payload.idempotency_key, reason=payload.reason):
        return
    record = await session.scalar(select(PlatformAdmin).where(PlatformAdmin.user_id == user_id))
    if record is None:
        record = PlatformAdmin(user_id=user_id, granted_by_user_id=context.user.id, status=PlatformAdminStatus.ACTIVE)
        session.add(record)
    else:
        record.status = PlatformAdminStatus.ACTIVE
        record.revoked_at = None
        record.granted_by_user_id = context.user.id
    await audit(session, context=context, request=request, action=action, target_type="user", target_id=user_id, reason=payload.reason, change_summary={"idempotency_key": payload.idempotency_key})
    await commit_admin_action(session, context=context, action=action, target_type="user", target_id=user_id, idempotency_key=payload.idempotency_key, reason=payload.reason)


@router.delete("/admins/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_admin(user_id: UUID, payload: AdminGrantRequest, request: Request, session: DbSession, context: CurrentAdmin) -> None:
    if user_id == context.user.id:
        raise HTTPException(status_code=422, detail="You cannot revoke your own platform access")
    action = "admin.platform_admin.revoke"
    if await admin_action_is_replay(session, context=context, action=action, target_type="user", target_id=user_id, idempotency_key=payload.idempotency_key, reason=payload.reason):
        return
    record = await session.scalar(select(PlatformAdmin).where(PlatformAdmin.user_id == user_id))
    if record is None:
        raise HTTPException(status_code=404, detail="Platform admin not found")
    record.status = PlatformAdminStatus.REVOKED
    record.revoked_at = datetime.now(UTC)
    await audit(session, context=context, request=request, action=action, target_type="user", target_id=user_id, reason=payload.reason, change_summary={"idempotency_key": payload.idempotency_key})
    await commit_admin_action(session, context=context, action=action, target_type="user", target_id=user_id, idempotency_key=payload.idempotency_key, reason=payload.reason)


__all__ = ["router"]
