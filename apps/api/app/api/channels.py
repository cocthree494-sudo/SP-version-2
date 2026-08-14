"""Tenant channel installation API.

This is the secure foundation for connector-specific flows. It records the
approved connection mode and scope, while provider OAuth/QR/OTP flows remain
outside the dashboard API and only return an opaque credential reference.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import AuthContext, CurrentAuth
from app.db.session import get_db_session
from app.domains.bots.models import Bot
from app.domains.channels.models import ChannelInstallation, ChannelStatus
from app.domains.channels.schemas import (
    ChannelInstallationResponse,
    ChannelInstallRequest,
    ChannelStatusUpdateRequest,
)
from app.domains.tenancy.enums import MembershipRole

router = APIRouter(prefix="/v1/channels", tags=["channels"])
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


def require_channel_manager(context: CurrentAuth) -> AuthContext:
    if context.membership.role not in {MembershipRole.OWNER, MembershipRole.ADMIN}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Owner or admin role is required"
        )
    return context


ChannelManager = Annotated[AuthContext, Depends(require_channel_manager)]


def _response(item: ChannelInstallation) -> ChannelInstallationResponse:
    return ChannelInstallationResponse.model_validate(item)


@router.get("", response_model=list[ChannelInstallationResponse])
async def list_channels(
    session: DbSession, context: CurrentAuth
) -> list[ChannelInstallationResponse]:
    result = await session.scalars(
        select(ChannelInstallation)
        .where(ChannelInstallation.tenant_id == context.tenant.id)
        .order_by(ChannelInstallation.created_at.desc())
    )
    return [_response(item) for item in result.all()]


@router.post("", response_model=ChannelInstallationResponse, status_code=status.HTTP_201_CREATED)
async def install_channel(
    payload: ChannelInstallRequest,
    session: DbSession,
    context: ChannelManager,
) -> ChannelInstallationResponse:
    bot = await session.scalar(
        select(Bot).where(Bot.id == payload.bot_id, Bot.tenant_id == context.tenant.id)
    )
    if bot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot not found")
    duplicate = await session.scalar(
        select(ChannelInstallation).where(
            ChannelInstallation.tenant_id == context.tenant.id,
            ChannelInstallation.external_identity == payload.external_identity,
            ChannelInstallation.channel_type == payload.channel_type,
            ChannelInstallation.status != ChannelStatus.REVOKED,
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This channel is already connected"
        )
    item = ChannelInstallation(
        tenant_id=context.tenant.id,
        bot_id=bot.id,
        channel_type=payload.channel_type,
        external_identity=payload.external_identity,
        status=ChannelStatus.PENDING,
        conversation_scope=payload.conversation_scope,
        consent_record={"acknowledged": True, "actor_id": str(context.user.id)},
        credential_reference=None,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return _response(item)


@router.patch("/{channel_id}", response_model=ChannelInstallationResponse)
async def update_channel(
    channel_id: UUID,
    payload: ChannelStatusUpdateRequest,
    session: DbSession,
    context: ChannelManager,
) -> ChannelInstallationResponse:
    item = await session.scalar(
        select(ChannelInstallation).where(
            ChannelInstallation.id == channel_id,
            ChannelInstallation.tenant_id == context.tenant.id,
        )
    )
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Channel installation not found"
        )
    if (
        item.status is ChannelStatus.REVOKED
        and payload.status is not None
        and payload.status is not ChannelStatus.REVOKED
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Revoked channels cannot be resumed"
        )
    if payload.bot_id is not None:
        bot = await session.scalar(
            select(Bot).where(Bot.id == payload.bot_id, Bot.tenant_id == context.tenant.id)
        )
        if bot is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot not found")
        item.bot_id = bot.id
    if payload.status is not None:
        # A connector, not a dashboard button, proves that its authorization
        # completed.  The UI may pause/revoke a connection, but cannot fake a
        # live external integration by marking a pending connector connected.
        if item.status is ChannelStatus.PENDING and payload.status is ChannelStatus.CONNECTED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Complete provider authorization before this channel can be connected",
            )
        item.status = payload.status
    await session.commit()
    await session.refresh(item)
    return _response(item)


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_channel(channel_id: UUID, session: DbSession, context: ChannelManager) -> Response:
    item = await session.scalar(
        select(ChannelInstallation).where(
            ChannelInstallation.id == channel_id,
            ChannelInstallation.tenant_id == context.tenant.id,
        )
    )
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Channel installation not found"
        )
    item.status = ChannelStatus.REVOKED
    item.credential_reference = None
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["require_channel_manager", "router"]
