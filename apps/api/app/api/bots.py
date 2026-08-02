"""Authenticated tenant dashboard API for bots and widget keys."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import AuthContext, CurrentAuth
from app.db.session import get_db_session
from app.domains.bots.schemas import (
    BotCreateRequest,
    BotKeyCreateRequest,
    BotKeyResponse,
    BotKeyUpdateRequest,
    BotResponse,
    BotUpdateRequest,
)
from app.domains.bots.service import (
    BotKeyNotFoundError,
    BotNotFoundError,
    BotService,
    RevokedBotKeyError,
)
from app.domains.tenancy.enums import MembershipRole

router = APIRouter(prefix="/v1/bots", tags=["bots"])
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


def require_bot_manager(context: CurrentAuth) -> AuthContext:
    if context.membership.role not in {MembershipRole.OWNER, MembershipRole.ADMIN}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner or admin role is required",
        )
    return context


BotManager = Annotated[AuthContext, Depends(require_bot_manager)]


def _service(session: AsyncSession, context: AuthContext) -> BotService:
    return BotService(session, context.tenant.id)


def _not_found(exc: BotNotFoundError | BotKeyNotFoundError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("", response_model=BotResponse, status_code=status.HTTP_201_CREATED)
async def create_bot(
    payload: BotCreateRequest,
    session: DbSession,
    context: BotManager,
) -> BotResponse:
    bot = await _service(session, context).create_bot(payload)
    return BotResponse.model_validate(bot)


@router.get("", response_model=list[BotResponse])
async def list_bots(session: DbSession, context: CurrentAuth) -> list[BotResponse]:
    bots = await _service(session, context).list_bots()
    return [BotResponse.model_validate(bot) for bot in bots]


@router.get("/{bot_id}", response_model=BotResponse)
async def get_bot(bot_id: UUID, session: DbSession, context: CurrentAuth) -> BotResponse:
    try:
        bot = await _service(session, context).get_bot(bot_id)
    except BotNotFoundError as exc:
        raise _not_found(exc) from None
    return BotResponse.model_validate(bot)


@router.patch("/{bot_id}", response_model=BotResponse)
async def update_bot(
    bot_id: UUID,
    payload: BotUpdateRequest,
    session: DbSession,
    context: BotManager,
) -> BotResponse:
    try:
        bot = await _service(session, context).update_bot(bot_id, payload)
    except BotNotFoundError as exc:
        raise _not_found(exc) from None
    return BotResponse.model_validate(bot)


@router.delete("/{bot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bot(bot_id: UUID, session: DbSession, context: BotManager) -> Response:
    try:
        await _service(session, context).delete_bot(bot_id)
    except BotNotFoundError as exc:
        raise _not_found(exc) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{bot_id}/keys",
    response_model=BotKeyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_bot_key(
    bot_id: UUID,
    payload: BotKeyCreateRequest,
    session: DbSession,
    context: BotManager,
) -> BotKeyResponse:
    try:
        key = await _service(session, context).create_key(bot_id, payload)
    except BotNotFoundError as exc:
        raise _not_found(exc) from None
    return BotKeyResponse.model_validate(key)


@router.get("/{bot_id}/keys", response_model=list[BotKeyResponse])
async def list_bot_keys(
    bot_id: UUID,
    session: DbSession,
    context: CurrentAuth,
) -> list[BotKeyResponse]:
    try:
        keys = await _service(session, context).list_keys(bot_id)
    except BotNotFoundError as exc:
        raise _not_found(exc) from None
    return [BotKeyResponse.model_validate(key) for key in keys]


@router.patch("/{bot_id}/keys/{key_id}", response_model=BotKeyResponse)
async def update_bot_key(
    bot_id: UUID,
    key_id: UUID,
    payload: BotKeyUpdateRequest,
    session: DbSession,
    context: BotManager,
) -> BotKeyResponse:
    try:
        key = await _service(session, context).update_key(bot_id, key_id, payload)
    except (BotNotFoundError, BotKeyNotFoundError) as exc:
        raise _not_found(exc) from None
    except RevokedBotKeyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    return BotKeyResponse.model_validate(key)


@router.delete("/{bot_id}/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_bot_key(
    bot_id: UUID,
    key_id: UUID,
    session: DbSession,
    context: BotManager,
) -> Response:
    try:
        await _service(session, context).revoke_key(bot_id, key_id)
    except (BotNotFoundError, BotKeyNotFoundError) as exc:
        raise _not_found(exc) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["require_bot_manager", "router"]
