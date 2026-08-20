"""Stable API contracts for the platform-admin control plane."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AdminPage(BaseModel):
    page: int
    page_size: int
    total: int
    pages: int


class AdminSummaryResponse(BaseModel):
    generated_at: datetime
    range_start: datetime | None
    range_end: datetime | None
    users: dict[str, int]
    tenants: dict[str, int]
    bots: int
    conversations: int
    usage: dict[str, int]
    ingestion: dict[str, int]
    channels: dict[str, int]
    voice: dict[str, int]
    security: dict[str, Any]
    readiness: dict[str, Any]
    usage_trend: list[dict[str, Any]]


class AdminTenantRow(BaseModel):
    tenant_id: UUID
    name: str
    slug: str
    status: str
    created_at: datetime
    member_count: int
    bot_count: int
    source_count: int
    conversation_count: int
    token_count: int
    estimated_cost_microusd: int
    last_activity_at: datetime | None


class AdminTenantListResponse(BaseModel):
    items: list[AdminTenantRow]
    page: AdminPage


class AdminUserRow(BaseModel):
    user_id: UUID
    email: str
    display_name: str | None
    status: str
    email_verified_at: datetime | None
    created_at: datetime
    tenant_count: int
    last_session_at: datetime | None
    active_session_count: int


class AdminUserListResponse(BaseModel):
    items: list[AdminUserRow]
    page: AdminPage


class AdminUserTenantRow(BaseModel):
    tenant_id: UUID
    name: str
    slug: str
    status: str
    role: str
    joined_at: datetime
    member_count: int
    bot_count: int
    source_count: int
    conversation_count: int
    token_count: int
    estimated_cost_microusd: int
    last_activity_at: datetime | None


class AdminUserBotRow(BaseModel):
    bot_id: UUID
    tenant_id: UUID
    tenant_name: str
    name: str
    status: str
    default_language: str
    widget_welcome_text: str
    widget_accent_color: str
    widget_position: str
    has_system_policy: bool
    system_policy_preview: str | None
    key_count: int
    active_key_count: int
    source_count: int
    conversation_count: int
    last_activity_at: datetime | None


class AdminUserSourceRow(BaseModel):
    source_id: UUID
    tenant_id: UUID
    tenant_name: str
    bot_id: UUID
    bot_name: str
    source_type: str
    name: str
    status: str
    details: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None
    error_message: str | None
    document_count: int
    active_document_count: int
    chunk_count: int
    content_preview: str | None = None
    updated_at: datetime


class AdminUserProviderRow(BaseModel):
    credential_id: UUID
    tenant_id: UUID
    tenant_name: str
    provider: str
    label: str
    low_cost_model_id: str
    strong_model_id: str | None
    status: str
    routing_mode: str | None
    verified_at: datetime | None
    rotated_at: datetime | None
    revoked_at: datetime | None


class AdminUserConversationRow(BaseModel):
    tenant_id: UUID
    tenant_name: str
    bot_id: UUID
    bot_name: str
    channel: str
    conversation_count: int
    message_count: int
    last_activity_at: datetime | None
    active_count: int


class AdminUserDetailResponse(BaseModel):
    user: AdminUserRow
    tenants: list[AdminUserTenantRow]
    bots: list[AdminUserBotRow]
    sources: list[AdminUserSourceRow]
    providers: list[AdminUserProviderRow]
    conversations: list[AdminUserConversationRow]
    content_included: bool = False


class AdminUsageRow(BaseModel):
    usage_event_id: UUID
    tenant_id: UUID
    tenant_name: str
    tenant_slug: str
    bot_id: UUID | None
    operation: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    latency_ms: int
    estimated_cost_microusd: int
    created_at: datetime


class AdminUsageListResponse(BaseModel):
    items: list[AdminUsageRow]
    page: AdminPage


class AdminIngestionRow(BaseModel):
    job_id: UUID
    tenant_id: UUID
    tenant_name: str
    source_id: UUID
    source_name: str | None
    job_type: str
    state: str
    attempts: int
    max_attempts: int
    progress_percent: int
    scheduled_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    error_code: str | None
    error_message: str | None
    created_at: datetime


class AdminIngestionListResponse(BaseModel):
    items: list[AdminIngestionRow]
    page: AdminPage


class AdminHealthRow(BaseModel):
    category: Literal["channel", "voice", "provider"]
    resource_id: UUID
    tenant_id: UUID
    tenant_name: str
    name: str
    status: str
    detail: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime | None = None


class AdminHealthListResponse(BaseModel):
    items: list[AdminHealthRow]
    page: AdminPage


class AdminAuditRow(BaseModel):
    id: UUID
    created_at: datetime
    actor_user_id: UUID | None
    action: str
    target_type: str
    target_id: UUID | None
    reason: str | None
    outcome: str
    request_id: str | None
    ip_address: str | None
    user_agent: str | None
    change_summary: dict[str, Any]


class AdminAuditListResponse(BaseModel):
    items: list[AdminAuditRow]
    page: AdminPage


class AdminActionRequest(BaseModel):
    status: Literal["active", "suspended", "disabled"]
    reason: str = Field(min_length=3, max_length=1000)
    confirmation: Literal["CONFIRM"]
    idempotency_key: str = Field(min_length=8, max_length=128)


class AdminRevokeSessionsRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)
    confirmation: Literal["CONFIRM"]
    idempotency_key: str = Field(min_length=8, max_length=128)


class AdminGrantRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)
    confirmation: Literal["CONFIRM"]
    idempotency_key: str = Field(min_length=8, max_length=128)


class AdminDirectoryRow(BaseModel):
    user_id: UUID
    email: str
    display_name: str | None
    status: str
    granted_at: datetime


__all__ = [name for name in globals() if name.startswith("Admin")]
