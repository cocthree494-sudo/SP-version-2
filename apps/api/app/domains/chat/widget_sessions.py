"""Short-lived origin-bound anonymous widget session tokens."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domains.bots.schemas import normalize_origin
from app.domains.bots.service import (
    get_publishable_key_tenant_id,
    resolve_widget_credential,
)
from app.domains.chat.repositories import ConversationRepository


class WidgetSessionTokenError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class WidgetSessionClaims:
    tenant_id: UUID
    bot_id: UUID
    key_id: UUID
    conversation_id: UUID
    token_id: UUID
    origin: str


@dataclass(frozen=True, slots=True)
class IssuedWidgetSession:
    token: str
    expires_in: int
    expires_at: datetime
    claims: WidgetSessionClaims


def create_widget_session_token(
    *,
    tenant_id: UUID,
    bot_id: UUID,
    key_id: UUID,
    conversation_id: UUID,
    origin: str,
) -> IssuedWidgetSession:
    now = datetime.now(UTC)
    expires_in = settings.WIDGET_SESSION_TTL_SECONDS
    expires_at = now + timedelta(seconds=expires_in)
    claims = WidgetSessionClaims(
        tenant_id=tenant_id,
        bot_id=bot_id,
        key_id=key_id,
        conversation_id=conversation_id,
        token_id=uuid4(),
        origin=normalize_origin(origin),
    )
    payload = {
        "sub": str(claims.conversation_id),
        "tenant_id": str(claims.tenant_id),
        "bot_id": str(claims.bot_id),
        "key_id": str(claims.key_id),
        "jti": str(claims.token_id),
        "origin": claims.origin,
        "type": "widget_session",
        "iat": now,
        "exp": expires_at,
        "iss": settings.AUTH_JWT_ISSUER,
        "aud": settings.WIDGET_SESSION_AUDIENCE,
    }
    token = jwt.encode(
        payload,
        settings.auth_jwt_secret,
        algorithm=settings.AUTH_JWT_ALGORITHM,
    )
    return IssuedWidgetSession(token, expires_in, expires_at, claims)


def decode_widget_session_token(token: str) -> WidgetSessionClaims:
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.auth_jwt_secret,
            algorithms=[settings.AUTH_JWT_ALGORITHM],
            audience=settings.WIDGET_SESSION_AUDIENCE,
            issuer=settings.AUTH_JWT_ISSUER,
            options={
                "require": [
                    "sub",
                    "tenant_id",
                    "bot_id",
                    "key_id",
                    "jti",
                    "origin",
                    "type",
                    "iat",
                    "exp",
                ]
            },
        )
        if payload["type"] != "widget_session":
            raise WidgetSessionTokenError("Unexpected token type")
        return WidgetSessionClaims(
            tenant_id=UUID(str(payload["tenant_id"])),
            bot_id=UUID(str(payload["bot_id"])),
            key_id=UUID(str(payload["key_id"])),
            conversation_id=UUID(str(payload["sub"])),
            token_id=UUID(str(payload["jti"])),
            origin=normalize_origin(str(payload["origin"])),
        )
    except WidgetSessionTokenError:
        raise
    except (KeyError, TypeError, ValueError, jwt.PyJWTError) as exc:
        raise WidgetSessionTokenError("Invalid widget session token") from exc


async def validate_widget_session(
    session: AsyncSession,
    *,
    token: str,
    publishable_key: str,
    origin: str,
) -> WidgetSessionClaims | None:
    """Re-check token, exact origin, key revocation, bot state, and conversation."""

    try:
        claims = decode_widget_session_token(token)
        normalized_origin = normalize_origin(origin)
        key_tenant_id = get_publishable_key_tenant_id(publishable_key)
    except (ValueError, WidgetSessionTokenError):
        return None
    if claims.tenant_id != key_tenant_id or claims.origin != normalized_origin:
        return None
    credential = await resolve_widget_credential(
        session,
        publishable_key=publishable_key,
        origin=normalized_origin,
    )
    if (
        credential is None
        or credential.tenant_id != claims.tenant_id
        or credential.bot_id != claims.bot_id
        or credential.key_id != claims.key_id
    ):
        return None
    conversation = await ConversationRepository(session, claims.tenant_id).get(
        claims.conversation_id
    )
    if conversation is None or conversation.bot_id != claims.bot_id:
        return None
    return claims


__all__ = [
    "IssuedWidgetSession",
    "WidgetSessionClaims",
    "WidgetSessionTokenError",
    "create_widget_session_token",
    "decode_widget_session_token",
    "validate_widget_session",
]

