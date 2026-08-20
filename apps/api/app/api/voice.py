"""Owner/admin voice-agent configuration and idempotent webhook intake."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import AuthContext, CurrentAuth
from app.core.config import settings
from app.db.session import get_db_session
from app.domains.bots.models import Bot
from app.domains.tenancy.enums import MembershipRole
from app.domains.voice.models import VoiceAgentInstallation, VoiceStatus, VoiceWebhookEvent
from app.domains.voice.schemas import (
    VoiceAgentResponse,
    VoiceInstallRequest,
    VoiceStatusUpdateRequest,
    VoiceWebhookRequest,
)

router = APIRouter(prefix="/v1/voice", tags=["voice"])
DbSession = Annotated[AsyncSession, Depends(get_db_session)]

_VOICE_UNAVAILABLE = (
    "Voice calling is not available yet. No approved telephony adapter is "
    "implemented, so a configured number can never receive calls."
)


def require_voice_enabled() -> None:
    """Fail closed while no telephony adapter exists.

    Storing an installation, letting a tenant mark it verified, or accepting a
    provider event would present an unimplemented capability as connected.
    """

    if not settings.VOICE_AGENTS_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_VOICE_UNAVAILABLE
        )


VoiceEnabled = Annotated[None, Depends(require_voice_enabled)]


def require_voice_manager(context: CurrentAuth) -> AuthContext:
    if context.membership.role not in {MembershipRole.OWNER, MembershipRole.ADMIN}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Owner or admin role is required"
        )
    return context


VoiceManager = Annotated[AuthContext, Depends(require_voice_manager)]


@router.get("", response_model=list[VoiceAgentResponse])
async def list_voice_agents(session: DbSession, context: CurrentAuth) -> list[VoiceAgentResponse]:
    rows = await session.scalars(
        select(VoiceAgentInstallation)
        .where(VoiceAgentInstallation.tenant_id == context.tenant.id)
        .order_by(VoiceAgentInstallation.created_at.desc())
    )
    return [VoiceAgentResponse.model_validate(row) for row in rows.all()]


@router.post("", response_model=VoiceAgentResponse, status_code=status.HTTP_201_CREATED)
async def install_voice_agent(
    payload: VoiceInstallRequest,
    session: DbSession,
    context: VoiceManager,
    _enabled: VoiceEnabled,
) -> VoiceAgentResponse:
    if payload.bot_id is not None:
        bot = await session.scalar(
            select(Bot).where(Bot.id == payload.bot_id, Bot.tenant_id == context.tenant.id)
        )
        if bot is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot not found")
    existing = await session.scalar(
        select(VoiceAgentInstallation).where(
            VoiceAgentInstallation.tenant_id == context.tenant.id,
            VoiceAgentInstallation.phone_number == payload.phone_number,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This phone number is already configured"
        )
    row = VoiceAgentInstallation(
        tenant_id=context.tenant.id,
        bot_id=payload.bot_id,
        provider=payload.provider,
        phone_number=payload.phone_number,
        language=payload.language,
        voice=payload.voice,
        business_hours=payload.business_hours,
        outbound_enabled=payload.outbound_enabled,
        recording_enabled=payload.recording_enabled,
        retention_days=payload.retention_days,
        monthly_cost_limit_usd=payload.monthly_cost_limit_usd,
        status=VoiceStatus.PENDING,
        provider_reference=None,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return VoiceAgentResponse.model_validate(row)


@router.patch("/{voice_id}", response_model=VoiceAgentResponse)
async def update_voice_agent(
    voice_id: UUID,
    payload: VoiceStatusUpdateRequest,
    session: DbSession,
    context: VoiceManager,
    _enabled: VoiceEnabled,
) -> VoiceAgentResponse:
    row = await session.scalar(
        select(VoiceAgentInstallation).where(
            VoiceAgentInstallation.id == voice_id,
            VoiceAgentInstallation.tenant_id == context.tenant.id,
        )
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice agent not found")
    row.status = payload.status
    await session.commit()
    await session.refresh(row)
    return VoiceAgentResponse.model_validate(row)


@router.post("/{voice_id}/webhooks", status_code=status.HTTP_202_ACCEPTED)
async def receive_voice_event(
    voice_id: UUID,
    payload: VoiceWebhookRequest,
    session: DbSession,
    _enabled: VoiceEnabled,
    _signature: Annotated[str | None, Header(alias="X-Provider-Signature")] = None,
) -> Response:
    # This route is unauthenticated by design: a telephony provider calls it.
    # The length check below is a placeholder, not verification. Before
    # VOICE_AGENTS_ENABLED is ever set, this must verify a real per-installation
    # provider HMAC and scope the lookup by tenant; otherwise any caller holding
    # an installation UUID can write rows into that tenant's event table.
    if _signature is None or len(_signature) < 32:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Provider signature is required"
        )
    row = await session.scalar(
        select(VoiceAgentInstallation).where(VoiceAgentInstallation.id == voice_id)
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice agent not found")
    duplicate = await session.scalar(
        select(VoiceWebhookEvent).where(
            VoiceWebhookEvent.tenant_id == row.tenant_id,
            VoiceWebhookEvent.event_id == payload.event_id,
        )
    )
    if duplicate is not None:
        return Response(status_code=status.HTTP_202_ACCEPTED)
    session.add(
        VoiceWebhookEvent(
            tenant_id=row.tenant_id,
            installation_id=row.id,
            event_id=payload.event_id,
            event_type=payload.event_type,
            payload=payload.payload,
        )
    )
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
    return Response(status_code=status.HTTP_202_ACCEPTED)


__all__ = ["require_voice_enabled", "require_voice_manager", "router"]
