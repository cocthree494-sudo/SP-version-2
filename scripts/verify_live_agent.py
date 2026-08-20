"""Live verification harness: drives the deployed grounded agent for one tenant/bot.

Mirrors apps/api/app/api/playground.py wiring exactly. Read-mostly: it creates
one playground conversation per question and persists the resulting turn, the
same as a real playground session would.
"""

from __future__ import annotations

import asyncio
import os
from uuid import UUID

from app.core.tenancy import set_database_tenant
from app.db.models import register_model_mappings
from app.db.session import get_session
from app.domains.chat.conversation_service import ConversationService
from app.domains.chat.orchestrator import (
    AgentStreamEventType,
    GroundedAnswerOrchestrator,
)
from app.domains.knowledge.retrieval import HybridRetrievalService
from app.providers.factory import build_embedding_provider
from app.providers.router import InMemoryCircuitStore, ModelRouter
from app.providers.tenant_factory import build_tenant_llm_targets

TENANT = UUID(os.environ["HARNESS_TENANT_ID"])
BOT = UUID(os.environ["HARNESS_BOT_ID"])

QUESTIONS = [
    ("greeting", "hi"),
    ("greeting", "hello"),
    ("keyword-match control", "What kind of work does NPC Automators do?"),
    ("paraphrase (no keyword overlap)", "what services do you offer?"),
]
if os.environ.get("HARNESS_QUESTIONS"):
    QUESTIONS = [
        ("probe", line.strip())
        for line in os.environ["HARNESS_QUESTIONS"].split("|")
        if line.strip()
    ]


async def ask(label: str, question: str) -> None:
    async for session in get_session():
        await set_database_tenant(session, TENANT)
        conversation = await ConversationService(session, TENANT).create(
            bot_id=BOT, channel="playground"
        )
        await session.commit()

        targets = await build_tenant_llm_targets(session, TENANT)
        router = ModelRouter(targets, InMemoryCircuitStore())
        agent = GroundedAnswerOrchestrator(
            session,
            TENANT,
            retriever=HybridRetrievalService(session, TENANT, build_embedding_provider()),
            router=router,
        )

        text_parts: list[str] = []
        final = None
        try:
            async for event in agent.stream_answer(
                conversation_id=conversation.id, question=question
            ):
                if event.type in {
                    AgentStreamEventType.TEXT_DELTA,
                    AgentStreamEventType.REPLACE_TEXT,
                }:
                    if event.type is AgentStreamEventType.REPLACE_TEXT:
                        text_parts = []
                    text_parts.append(event.text or "")
                elif event.answer is not None:
                    final = event.answer
            await session.commit()
        finally:
            await router.aclose()

        answer = "".join(text_parts).strip()
        print(f"--- {label}: {question!r}")
        print(f"    answer      : {answer[:180]}")
        if final is not None:
            print(f"    kind        : {getattr(final, 'response_kind', '<absent>')}")
            print(f"    fallback    : {final.fallback}")
            print(f"    provider    : {final.provider_id}")
            print(f"    model       : {final.model_id}")
            print(f"    citations   : {len(final.citations)}")
        print(f"    conversation: {conversation.id}")
        print()
        return


async def main() -> None:
    register_model_mappings()
    for label, question in QUESTIONS:
        try:
            await ask(label, question)
        except Exception as exc:  # noqa: BLE001 - diagnostic harness
            print(f"--- {label}: {question!r}\n    FAILED: {type(exc).__name__}: {exc}\n")


asyncio.run(main())
