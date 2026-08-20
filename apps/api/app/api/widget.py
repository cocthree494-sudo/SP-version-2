"""Origin-checked anonymous widget sessions and SSE chat."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.tenancy import tenant_session_scope
from app.db.session import get_db_session
from app.domains.bots.schemas import normalize_origin
from app.domains.bots.service import ResolvedWidgetCredential, resolve_widget_credential
from app.domains.chat.conversation_service import ConversationService
from app.domains.chat.orchestrator import (
    AgentStreamEvent,
    AgentStreamEventType,
    GroundedAnswerOrchestrator,
)
from app.domains.chat.rate_limit import (
    InMemoryRateLimiter,
    RateLimiter,
    RateLimiterUnavailableError,
    public_rate_limit_key,
)
from app.domains.chat.schemas import WidgetMessageRequest, WidgetSessionResponse
from app.domains.chat.widget_sessions import (
    WidgetSessionClaims,
    create_widget_session_token,
    validate_widget_session,
)
from app.domains.knowledge.retrieval import HybridRetrievalService
from app.providers.factory import build_embedding_provider
from app.providers.router import CircuitStore, InMemoryCircuitStore, ModelRouter
from app.providers.tenant_factory import (
    TenantProviderUnavailableError,
    build_tenant_llm_targets,
)

router = APIRouter(prefix="/v1/widget", tags=["widget"])
widget_bearer = HTTPBearer(auto_error=False, scheme_name="WidgetSessionBearer")
DbSession = Annotated[AsyncSession, Depends(get_db_session)]
OriginHeader = Annotated[str, Header(alias="Origin", min_length=1, max_length=2048)]
WidgetCredentials = Annotated[
    HTTPAuthorizationCredentials | None,
    Depends(widget_bearer),
]


def get_widget_rate_limiter(request: Request) -> RateLimiter:
    limiter = getattr(request.app.state, "widget_rate_limiter", None)
    if limiter is not None:
        return limiter
    if settings.is_local:
        # Unit/ASGI tests may run without lifespan; production fails closed.
        limiter = InMemoryRateLimiter()
        request.app.state.widget_rate_limiter = limiter
        return limiter
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Public chat rate limiter is unavailable",
    )


def get_model_circuit_store(request: Request) -> CircuitStore:
    store = getattr(request.app.state, "model_circuit_store", None)
    if store is not None:
        return store
    if settings.is_local:
        store = InMemoryCircuitStore()
        request.app.state.model_circuit_store = store
        return store
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="AI routing state is unavailable",
    )


RateLimitDependency = Annotated[RateLimiter, Depends(get_widget_rate_limiter)]
CircuitDependency = Annotated[CircuitStore, Depends(get_model_circuit_store)]


def _cors_headers(origin: str) -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Authorization, Content-Type",
        "Access-Control-Max-Age": "600",
        "Vary": "Origin",
    }


def _stream_headers(origin: str) -> dict[str, str]:
    return {
        **_cors_headers(origin),
        "Cache-Control": "no-cache, no-store",
        "X-Accel-Buffering": "no",
    }


def _forbidden_widget() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Widget key or origin is not allowed",
    )


def _unauthorized_widget() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired widget session",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def _allowed_origin(
    session: AsyncSession,
    *,
    publishable_key: str,
    origin: str,
) -> tuple[str, ResolvedWidgetCredential]:
    try:
        normalized_origin = normalize_origin(origin)
    except ValueError:
        raise _forbidden_widget() from None
    credential = await resolve_widget_credential(
        session,
        publishable_key=publishable_key,
        origin=normalized_origin,
    )
    if credential is None:
        raise _forbidden_widget()
    return normalized_origin, credential


async def _consume_rate_limit(
    limiter: RateLimiter,
    *,
    key: str,
    limit: int,
    window_seconds: int,
) -> None:
    try:
        decision = await limiter.consume(
            key=key,
            limit=limit,
            window_seconds=window_seconds,
        )
    except RateLimiterUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from None
    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Public chat rate limit exceeded",
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )


@router.options("/{publishable_key}/sessions", status_code=status.HTTP_204_NO_CONTENT)
@router.options("/{publishable_key}/messages", status_code=status.HTTP_204_NO_CONTENT)
async def widget_preflight(
    publishable_key: str,
    origin: OriginHeader,
    session: DbSession,
) -> Response:
    normalized_origin, _credential = await _allowed_origin(
        session,
        publishable_key=publishable_key,
        origin=origin,
    )
    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
        headers=_cors_headers(normalized_origin),
    )


@router.post(
    "/{publishable_key}/sessions",
    response_model=WidgetSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_widget_session(
    publishable_key: str,
    request: Request,
    origin: OriginHeader,
    session: DbSession,
    limiter: RateLimitDependency,
) -> JSONResponse:
    normalized_origin, raw_credential = await _allowed_origin(
        session,
        publishable_key=publishable_key,
        origin=origin,
    )
    credential = raw_credential
    identity = request.client.host if request.client is not None else "unknown"
    await _consume_rate_limit(
        limiter,
        key=public_rate_limit_key(
            tenant_id=credential.tenant_id,
            bot_id=credential.bot_id,
            scope="session",
            identity=identity,
        ),
        limit=settings.WIDGET_SESSION_RATE_LIMIT,
        window_seconds=settings.WIDGET_SESSION_RATE_WINDOW_SECONDS,
    )
    try:
        async with tenant_session_scope(session, credential.tenant_id):
            conversation = await ConversationService(session, credential.tenant_id).create(
                bot_id=credential.bot_id,
                channel="widget",
            )
            issued = create_widget_session_token(
                tenant_id=credential.tenant_id,
                bot_id=credential.bot_id,
                key_id=credential.key_id,
                conversation_id=conversation.id,
                origin=normalized_origin,
            )
            await session.commit()
    except Exception:
        await session.rollback()
        raise
    payload = WidgetSessionResponse(
        session_token=issued.token,
        expires_in=issued.expires_in,
        expires_at=issued.expires_at,
        conversation_id=conversation.id,
    )
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=payload.model_dump(mode="json"),
        headers={**_cors_headers(normalized_origin), "Cache-Control": "no-store"},
    )


async def _validated_claims(
    session: AsyncSession,
    *,
    credentials: HTTPAuthorizationCredentials | None,
    publishable_key: str,
    origin: str,
) -> WidgetSessionClaims:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise _unauthorized_widget()
    claims = await validate_widget_session(
        session,
        token=credentials.credentials,
        publishable_key=publishable_key,
        origin=origin,
    )
    if claims is None:
        raise _unauthorized_widget()
    return claims


def _sse(event: str, payload: object) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


def _event_payload(event: AgentStreamEvent) -> object:
    if event.type in {AgentStreamEventType.TEXT_DELTA, AgentStreamEventType.REPLACE_TEXT}:
        return {"text": event.text}
    if event.type is AgentStreamEventType.CITATIONS:
        return {"citations": [asdict(item) for item in event.citations or []]}
    if event.answer is None:
        return {}
    return {
        "conversation_id": str(event.answer.conversation_id),
        "user_message_id": str(event.answer.user_message_id),
        "assistant_message_id": str(event.answer.assistant_message_id),
        "fallback": event.answer.fallback,
        "provider_id": event.answer.provider_id,
        "model_id": event.answer.model_id,
        "routing_reason": event.answer.routing_reason,
        "response_kind": event.answer.response_kind,
    }


@router.post("/{publishable_key}/messages")
async def stream_widget_message(
    publishable_key: str,
    payload: WidgetMessageRequest,
    request: Request,
    origin: OriginHeader,
    credentials: WidgetCredentials,
    session: DbSession,
    limiter: RateLimitDependency,
    circuits: CircuitDependency,
) -> StreamingResponse:
    try:
        normalized_origin = normalize_origin(origin)
    except ValueError:
        raise _unauthorized_widget() from None
    claims = await _validated_claims(
        session,
        credentials=credentials,
        publishable_key=publishable_key,
        origin=normalized_origin,
    )
    await _consume_rate_limit(
        limiter,
        key=public_rate_limit_key(
            tenant_id=claims.tenant_id,
            bot_id=claims.bot_id,
            scope="message",
            identity=str(claims.token_id),
        ),
        limit=settings.WIDGET_MESSAGE_RATE_LIMIT,
        window_seconds=settings.WIDGET_MESSAGE_RATE_WINDOW_SECONDS,
    )
    embedding_provider = build_embedding_provider()
    try:
        targets = await build_tenant_llm_targets(session, claims.tenant_id)
    except TenantProviderUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from None
    model_router = ModelRouter(targets, circuits)
    agent = GroundedAnswerOrchestrator(
        session,
        claims.tenant_id,
        retriever=HybridRetrievalService(session, claims.tenant_id, embedding_provider),
        router=model_router,
    )

    async def event_stream() -> AsyncIterator[str]:
        stream = agent.stream_answer(
            conversation_id=claims.conversation_id,
            question=payload.message,
        )
        try:
            yield _sse("ready", {"conversation_id": str(claims.conversation_id)})
            async for event in stream:
                if await request.is_disconnected():
                    break
                yield _sse(event.type.value, _event_payload(event))
        except asyncio.CancelledError:
            raise
        except Exception:
            await session.rollback()
            yield _sse(
                "error",
                {"message": "The support agent could not complete this request."},
            )
        finally:
            close_stream = getattr(stream, "aclose", None)
            if close_stream is not None:
                await close_stream()
            await model_router.aclose()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=_stream_headers(normalized_origin),
    )


__all__ = [
    "get_model_circuit_store",
    "get_widget_rate_limiter",
    "router",
]
