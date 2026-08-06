"""Authenticated tenant playground sessions and grounded SSE chat."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import asdict
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import CurrentAuth
from app.api.widget import CircuitDependency
from app.db.session import get_db_session
from app.domains.chat.conversation_service import (
    ConversationDomainError,
    ConversationNotFoundError,
    ConversationService,
)
from app.domains.chat.orchestrator import (
    AgentStreamEvent,
    AgentStreamEventType,
    GroundedAnswerOrchestrator,
)
from app.domains.chat.schemas import (
    PlaygroundSessionRequest,
    PlaygroundSessionResponse,
    WidgetMessageRequest,
)
from app.domains.knowledge.retrieval import HybridRetrievalService
from app.providers.factory import build_embedding_provider
from app.providers.router import ModelRouter
from app.providers.tenant_factory import (
    TenantProviderUnavailableError,
    build_tenant_llm_targets,
)

router = APIRouter(prefix="/v1/playground", tags=["playground"])
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


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
        "fallback": event.answer.fallback,
        "provider_id": event.answer.provider_id,
        "model_id": event.answer.model_id,
        "routing_reason": event.answer.routing_reason,
    }


@router.post(
    "/sessions",
    response_model=PlaygroundSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_playground_session(
    payload: PlaygroundSessionRequest,
    session: DbSession,
    context: CurrentAuth,
) -> PlaygroundSessionResponse:
    try:
        conversation = await ConversationService(session, context.tenant.id).create(
            bot_id=payload.bot_id,
            channel="playground",
        )
        await session.commit()
    except ConversationDomainError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from None
    return PlaygroundSessionResponse(conversation_id=conversation.id)


@router.post("/sessions/{conversation_id}/messages")
async def stream_playground_message(
    conversation_id: UUID,
    payload: WidgetMessageRequest,
    request: Request,
    session: DbSession,
    context: CurrentAuth,
    circuits: CircuitDependency,
) -> StreamingResponse:
    try:
        conversation_context = await ConversationService(
            session, context.tenant.id
        ).load_context(conversation_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playground conversation not found",
        ) from exc
    if conversation_context.conversation.channel != "playground":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playground conversation not found",
        )
    try:
        targets = await build_tenant_llm_targets(session, context.tenant.id)
    except TenantProviderUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from None
    model_router = ModelRouter(targets, circuits)
    embedding_provider = build_embedding_provider()
    agent = GroundedAnswerOrchestrator(
        session,
        context.tenant.id,
        retriever=HybridRetrievalService(session, context.tenant.id, embedding_provider),
        router=model_router,
    )

    async def event_stream() -> AsyncIterator[str]:
        stream = agent.stream_answer(
            conversation_id=conversation_id,
            question=payload.message,
        )
        try:
            yield _sse("ready", {"conversation_id": str(conversation_id)})
            async for event in stream:
                if await request.is_disconnected():
                    break
                yield _sse(event.type.value, _event_payload(event))
        except asyncio.CancelledError:
            raise
        except Exception:
            await session.rollback()
            yield _sse("error", {"message": "The playground could not complete this turn."})
        finally:
            close_stream = getattr(stream, "aclose", None)
            if close_stream is not None:
                await close_stream()
            await model_router.aclose()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-store", "X-Accel-Buffering": "no"},
    )


__all__ = ["router"]
