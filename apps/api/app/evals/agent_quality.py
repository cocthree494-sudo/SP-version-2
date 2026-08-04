"""Credential-free repeatable quality/safety evaluation runner."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TypedDict, cast
from uuid import UUID, uuid4

from sqlalchemy import Table, make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.tenancy import set_database_tenant
from app.db.base import Base
from app.domains.bots.models import Bot
from app.domains.chat.conversation_service import ConversationNotFoundError, ConversationService
from app.domains.chat.models import Conversation, ConversationMessage
from app.domains.chat.orchestrator import GroundedAnswerOrchestrator
from app.domains.knowledge.retrieval import Citation, RetrievalResult
from app.domains.tenancy.models import Tenant
from app.domains.usage.models import UsageEvent
from app.providers.router import InMemoryCircuitStore, ModelRouter, ModelTarget, ModelTier
from app.providers.types import (
    GenerationRequest,
    GenerationResponse,
    ProviderUsage,
    StreamEvent,
    StreamEventType,
)


class EvaluationCase(TypedDict):
    id: str
    category: str
    question: str
    evidence: str | None
    retrieval_score: float
    response: str
    strong_response: str
    expected_fallback: bool
    expected_text_contains: str
    expected_citation_count: int
    injection_marker: str | None
    cross_tenant: bool


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    case_id: str
    category: str
    passed: bool
    checks: list[str]
    failures: list[str]


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    total: int
    passed: int
    failed: int
    results: list[EvaluationResult]

    def as_json(self) -> dict[str, object]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "results": [asdict(result) for result in self.results],
        }


class _EvaluationProvider:
    provider_id = "deterministic-eval"

    def __init__(self, model_id: str, text: str) -> None:
        self.model_id = model_id
        self.text = text
        self.requests: list[GenerationRequest] = []

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.requests.append(request)
        return GenerationResponse(
            text=self.text,
            finish_reason="stop",
            usage=ProviderUsage(input_tokens=50, output_tokens=15),
            provider_id=self.provider_id,
            model_id=self.model_id,
        )

    async def stream(self, request: GenerationRequest) -> AsyncIterator[StreamEvent]:
        response = await self.generate(request)
        yield StreamEvent(type=StreamEventType.TEXT_DELTA, text=response.text)
        yield StreamEvent(
            type=StreamEventType.COMPLETED,
            finish_reason=response.finish_reason,
            usage=response.usage,
        )


class _EvaluationRetriever:
    def __init__(self, case: EvaluationCase) -> None:
        self.case = case
        self.calls = 0

    async def retrieve(
        self,
        *,
        bot_id: UUID,
        query: str,
        top_k: int = 6,
        source_ids: set[UUID] | None = None,
        language: str | None = None,
    ) -> list[RetrievalResult]:
        del bot_id, query, top_k, source_ids, language
        self.calls += 1
        evidence = self.case["evidence"]
        if evidence is None:
            return []
        return [
            RetrievalResult(
                chunk_id=uuid4(),
                content=evidence,
                score=self.case["retrieval_score"],
                vector_score=0.8,
                lexical_score=0.8,
                citation=Citation(
                    source_id=uuid4(),
                    document_id=uuid4(),
                    title="Evaluation fixture",
                    canonical_url="https://eval.example/source",
                    chunk_ordinal=0,
                    start_char=0,
                    end_char=len(evidence),
                ),
                metadata={"fixture": self.case["id"]},
            )
        ]


def load_cases(path: Path | None = None) -> list[EvaluationCase]:
    cases_path = path or Path(__file__).resolve().parents[2] / "evals" / "agent_quality_cases.json"
    raw = json.loads(cases_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Evaluation case file must contain a JSON list")
    return cast(list[EvaluationCase], raw)


async def _seed_conversation(
    session: AsyncSession,
    slug: str,
) -> tuple[Tenant, Bot, Conversation]:
    tenant = Tenant(name=slug, slug=slug)
    session.add(tenant)
    await session.flush()
    await set_database_tenant(session, tenant.id)
    bot = Bot(tenant_id=tenant.id, name="Evaluation bot", default_language="auto")
    session.add(bot)
    await session.flush()
    conversation = await ConversationService(session, tenant.id).create(
        bot_id=bot.id,
        channel="evaluation",
    )
    await session.commit()
    return tenant, bot, conversation


def _check(
    condition: bool,
    label: str,
    checks: list[str],
    failures: list[str],
) -> None:
    (checks if condition else failures).append(label)


async def _run_case(session: AsyncSession, case: EvaluationCase) -> EvaluationResult:
    checks: list[str] = []
    failures: list[str] = []
    safe_slug = f"eval-{case['id'].replace('_', '-')[:35]}-{uuid4().hex[:12]}"
    tenant, _bot, conversation = await _seed_conversation(session, safe_slug)
    low = _EvaluationProvider("low", case["response"])
    strong = _EvaluationProvider("strong", case["strong_response"])
    retriever = _EvaluationRetriever(case)
    agent = GroundedAnswerOrchestrator(
        session,
        tenant.id,
        retriever=retriever,
        router=ModelRouter(
            [
                ModelTarget(low, ModelTier.LOW_COST),
                ModelTarget(strong, ModelTier.STRONG),
            ],
            InMemoryCircuitStore(),
            retry_base_seconds=0,
        ),
    )

    try:
        if case["cross_tenant"]:
            other_tenant, _other_bot, other_conversation = await _seed_conversation(
                session,
                f"{safe_slug}-other",
            )
            del other_tenant
            try:
                await agent.answer(
                    conversation_id=other_conversation.id,
                    question=case["question"],
                )
            except ConversationNotFoundError:
                _check(True, "cross-tenant conversation rejected", checks, failures)
            else:
                _check(False, "cross-tenant conversation rejected", checks, failures)
            _check(retriever.calls == 0, "retrieval not reached", checks, failures)
            _check(not low.requests, "model not reached", checks, failures)
        else:
            answer = await agent.answer(
                conversation_id=conversation.id,
                question=case["question"],
            )
            _check(
                answer.fallback is case["expected_fallback"],
                "fallback state",
                checks,
                failures,
            )
            _check(
                case["expected_text_contains"] in answer.text,
                "expected response text",
                checks,
                failures,
            )
            _check(
                len(answer.citations) == case["expected_citation_count"],
                "citation count",
                checks,
                failures,
            )
            marker = case["injection_marker"]
            if marker is not None:
                request = low.requests[0]
                _check(
                    marker not in request.messages[0].content,
                    "injection absent from trusted system prompt",
                    checks,
                    failures,
                )
                _check(
                    any(
                        message.role.value == "tool" and marker in message.content
                        for message in request.messages
                    ),
                    "injection retained only as untrusted tool data",
                    checks,
                    failures,
                )
    except Exception as exc:
        await session.rollback()
        failures.append(f"unexpected {type(exc).__name__}: {exc}")

    return EvaluationResult(
        case_id=case["id"],
        category=case["category"],
        passed=not failures,
        checks=checks,
        failures=failures,
    )


async def run_evaluation(
    cases: list[EvaluationCase] | None = None,
    *,
    database_url: str | None = None,
    sqlite: bool = False,
) -> EvaluationReport:
    """Run cases against PostgreSQL or an explicitly selected SQLite fixture.

    ``TEST_DATABASE_URL`` is the default release path. SQLite is retained only
    for fast local iteration and must be requested with ``sqlite=True``.
    """

    selected = cases or load_cases()
    if sqlite:
        if database_url is not None:
            raise ValueError("database_url and sqlite=True cannot be used together")
        database_url = "sqlite+aiosqlite:///:memory:"
    resolved_url = database_url or settings.TEST_DATABASE_URL
    if resolved_url is None:
        raise ValueError(
            "A PostgreSQL TEST_DATABASE_URL is required for release evaluation; "
            "pass sqlite=True for an explicit fast local run"
        )
    engine = create_async_engine(
        resolved_url,
        poolclass=StaticPool if make_url(resolved_url).get_backend_name() == "sqlite" else None,
    )
    if make_url(resolved_url).get_backend_name() == "sqlite":
        tables = [
            cast(Table, Tenant.__table__),
            cast(Table, Bot.__table__),
            cast(Table, Conversation.__table__),
            cast(Table, ConversationMessage.__table__),
            cast(Table, UsageEvent.__table__),
        ]
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all, tables=tables)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            results = [await _run_case(session, case) for case in selected]
    finally:
        await engine.dispose()
    passed = sum(result.passed for result in results)
    return EvaluationReport(
        total=len(results),
        passed=passed,
        failed=len(results) - passed,
        results=results,
    )


def _print_human(report: EvaluationReport) -> None:
    state = "PASS" if report.failed == 0 else "FAIL"
    lines = [f"Agent quality evaluation: {state} ({report.passed}/{report.total})"]
    for result in report.results:
        label = "PASS" if result.passed else "FAIL"
        lines.append(f"{label} {result.case_id} [{result.category}]")
        for failure in result.failures:
            lines.append(f"  - {failure}")
    sys.stdout.write("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print the report as JSON")
    parser.add_argument(
        "--database-url",
        default=settings.TEST_DATABASE_URL,
        help="Migrated PostgreSQL URL; defaults to TEST_DATABASE_URL",
    )
    parser.add_argument(
        "--sqlite",
        action="store_true",
        help="Explicitly use the in-memory SQLite fixture for fast local iteration",
    )
    args = parser.parse_args()
    if not args.sqlite and args.database_url is None:
        parser.error(
            "release evaluation needs TEST_DATABASE_URL or --database-url; "
            "use --sqlite locally"
        )
    report = asyncio.run(
        run_evaluation(
            database_url=args.database_url,
            sqlite=args.sqlite,
        )
    )
    if args.json:
        sys.stdout.write(json.dumps(report.as_json(), ensure_ascii=False, indent=2) + "\n")
    else:
        _print_human(report)
    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
