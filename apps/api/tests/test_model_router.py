"""Model promotion, bounded retry, failover, and circuit simulations."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from app.providers.router import (
    AllProvidersUnavailableError,
    InMemoryCircuitStore,
    ModelRouter,
    ModelTarget,
    ModelTier,
    RoutingContext,
    RoutingReason,
)
from app.providers.types import (
    ChatMessage,
    GenerationRequest,
    GenerationResponse,
    MessageRole,
    ProviderError,
    ProviderErrorCategory,
    ProviderUsage,
    StreamEvent,
    StreamEventType,
)


class SimulatedProvider:
    def __init__(
        self,
        provider_id: str,
        model_id: str,
        outcomes: list[GenerationResponse | ProviderError],
    ) -> None:
        self.provider_id = provider_id
        self.model_id = model_id
        self.outcomes = outcomes
        self.calls = 0

    async def generate(self, _request: GenerationRequest) -> GenerationResponse:
        outcome = self.outcomes[min(self.calls, len(self.outcomes) - 1)]
        self.calls += 1
        if isinstance(outcome, ProviderError):
            raise outcome
        return outcome

    async def stream(self, request: GenerationRequest) -> AsyncIterator[StreamEvent]:
        response = await self.generate(request)
        yield StreamEvent(type=StreamEventType.TEXT_DELTA, text=response.text)
        yield StreamEvent(
            type=StreamEventType.COMPLETED,
            finish_reason=response.finish_reason,
            usage=response.usage,
        )


def response(provider: str, model: str, text: str) -> GenerationResponse:
    return GenerationResponse(
        text=text,
        finish_reason="stop",
        usage=ProviderUsage(input_tokens=5, output_tokens=3),
        provider_id=provider,
        model_id=model,
    )


def unavailable(provider: str) -> ProviderError:
    return ProviderError(
        ProviderErrorCategory.UNAVAILABLE,
        "Provider unavailable",
        provider_id=provider,
    )


def request() -> GenerationRequest:
    return GenerationRequest(
        messages=[ChatMessage(role=MessageRole.USER, content="Help me")]
    )


@pytest.mark.asyncio
async def test_router_defaults_low_cost_and_promotes_observably() -> None:
    low = SimulatedProvider("mock", "low", [response("mock", "low", "cheap")])
    strong = SimulatedProvider("mock", "strong", [response("mock", "strong", "deep")])
    router = ModelRouter(
        [ModelTarget(low, ModelTier.LOW_COST), ModelTarget(strong, ModelTier.STRONG)],
        InMemoryCircuitStore(),
        retry_base_seconds=0,
    )

    default = await router.generate(request(), RoutingContext(retrieval_score=0.8))
    promoted = await router.generate(
        request(),
        RoutingContext(complexity_score=1.0),
    )

    assert default.target.tier is ModelTier.LOW_COST
    assert default.routing_reason is RoutingReason.DEFAULT
    assert promoted.target.tier is ModelTier.STRONG
    assert promoted.routing_reason is RoutingReason.COMPLEX_QUERY


@pytest.mark.asyncio
async def test_router_retries_then_fails_over_and_opens_circuit() -> None:
    low = SimulatedProvider("first", "low", [unavailable("first")])
    strong = SimulatedProvider("second", "strong", [response("second", "strong", "ok")])
    circuits = InMemoryCircuitStore(failure_threshold=2, cooldown_seconds=60)
    router = ModelRouter(
        [ModelTarget(low, ModelTier.LOW_COST), ModelTarget(strong, ModelTier.STRONG)],
        circuits,
        max_retries_per_target=1,
        retry_base_seconds=0,
    )

    routed = await router.generate(request(), RoutingContext())

    assert low.calls == 2
    assert strong.calls == 1
    assert routed.routing_reason is RoutingReason.PROVIDER_FAILOVER
    assert await circuits.is_available("first:low") is False
    assert [attempt.error_category for attempt in routed.attempts[:2]] == [
        ProviderErrorCategory.UNAVAILABLE,
        ProviderErrorCategory.UNAVAILABLE,
    ]


@pytest.mark.asyncio
async def test_router_streams_selected_target_and_fails_safely() -> None:
    low = SimulatedProvider("mock", "low", [response("mock", "low", "streamed")])
    router = ModelRouter(
        [ModelTarget(low, ModelTier.LOW_COST)],
        InMemoryCircuitStore(),
        retry_base_seconds=0,
    )
    events = [event async for event in router.stream(request(), RoutingContext())]
    assert "".join(item.event.text for item in events) == "streamed"
    assert events[-1].event.type is StreamEventType.COMPLETED

    failing = SimulatedProvider("mock", "bad", [unavailable("mock")])
    failed_router = ModelRouter(
        [ModelTarget(failing, ModelTier.LOW_COST)],
        InMemoryCircuitStore(),
        max_retries_per_target=0,
        retry_base_seconds=0,
    )
    with pytest.raises(AllProvidersUnavailableError):
        await failed_router.generate(request(), RoutingContext())
