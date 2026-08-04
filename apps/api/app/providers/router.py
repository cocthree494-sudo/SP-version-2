"""Observable low-cost-first model routing, retry, failover, and circuits."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol, cast

from redis.asyncio import Redis

from app.core.config import settings
from app.providers.llm import LLMProvider
from app.providers.types import (
    GenerationRequest,
    GenerationResponse,
    ProviderError,
    ProviderErrorCategory,
    StreamEvent,
)


class ModelTier(StrEnum):
    LOW_COST = "low_cost"
    STRONG = "strong"


class RoutingReason(StrEnum):
    DEFAULT = "default_low_cost"
    WEAK_RETRIEVAL = "weak_retrieval"
    COMPLEX_QUERY = "complex_query"
    POLICY = "policy_requires_strong"
    VALIDATION_RETRY = "validation_retry"
    PROVIDER_FAILOVER = "provider_failover"


@dataclass(frozen=True, slots=True)
class RoutingContext:
    retrieval_score: float | None = None
    complexity_score: float = 0.0
    policy_requires_strong: bool = False
    validation_failed: bool = False


@dataclass(frozen=True, slots=True)
class ModelTarget:
    provider: LLMProvider
    tier: ModelTier
    input_cost_microusd_per_million: int = 0
    output_cost_microusd_per_million: int = 0

    @property
    def key(self) -> str:
        return f"{self.provider.provider_id}:{self.provider.model_id}"


@dataclass(frozen=True, slots=True)
class RouteAttempt:
    target_key: str
    attempt: int
    error_category: ProviderErrorCategory | None = None


@dataclass(frozen=True, slots=True)
class RoutedGeneration:
    response: GenerationResponse
    target: ModelTarget
    routing_reason: RoutingReason
    initial_reason: RoutingReason
    attempts: list[RouteAttempt]


@dataclass(frozen=True, slots=True)
class RoutedStreamEvent:
    event: StreamEvent
    target: ModelTarget
    routing_reason: RoutingReason
    initial_reason: RoutingReason
    attempt: int


class AllProvidersUnavailableError(RuntimeError):
    """Safe terminal error when no configured target can complete a request."""


class CircuitStore(Protocol):
    async def is_available(self, target_key: str) -> bool: ...

    async def record_success(self, target_key: str) -> None: ...

    async def record_failure(self, target_key: str) -> None: ...


@dataclass(slots=True)
class _CircuitState:
    failures: int = 0
    open_until: datetime | None = None


class InMemoryCircuitStore:
    def __init__(
        self,
        *,
        failure_threshold: int | None = None,
        cooldown_seconds: int | None = None,
    ) -> None:
        self.failure_threshold = (
            settings.MODEL_ROUTER_CIRCUIT_FAILURE_THRESHOLD
            if failure_threshold is None
            else failure_threshold
        )
        self.cooldown_seconds = (
            settings.MODEL_ROUTER_CIRCUIT_COOLDOWN_SECONDS
            if cooldown_seconds is None
            else cooldown_seconds
        )
        self._states: dict[str, _CircuitState] = {}

    async def is_available(self, target_key: str) -> bool:
        state = self._states.get(target_key)
        if state is None or state.open_until is None:
            return True
        if state.open_until <= datetime.now(UTC):
            self._states[target_key] = _CircuitState()
            return True
        return False

    async def record_success(self, target_key: str) -> None:
        self._states[target_key] = _CircuitState()

    async def record_failure(self, target_key: str) -> None:
        state = self._states.setdefault(target_key, _CircuitState())
        state.failures += 1
        if state.failures >= self.failure_threshold:
            state.open_until = datetime.now(UTC) + timedelta(seconds=self.cooldown_seconds)


class RedisCircuitStore:
    """Short-lived provider/model circuit state shared across API processes."""

    def __init__(self, redis: Redis, *, key_prefix: str = "provider-circuit") -> None:
        self.redis = redis
        self.key_prefix = key_prefix

    def _key(self, target_key: str) -> str:
        return f"{self.key_prefix}:{target_key}"

    async def is_available(self, target_key: str) -> bool:
        opened_until = await cast(
            Awaitable[str | None],
            self.redis.hget(self._key(target_key), "open_until"),
        )
        if opened_until is None:
            return True
        try:
            opened_timestamp = float(opened_until)
        except (TypeError, ValueError):
            await self.redis.delete(self._key(target_key))
            return True
        if opened_timestamp <= datetime.now(UTC).timestamp():
            await self.redis.delete(self._key(target_key))
            return True
        return False

    async def record_success(self, target_key: str) -> None:
        await self.redis.delete(self._key(target_key))

    async def record_failure(self, target_key: str) -> None:
        key = self._key(target_key)
        failures = await cast(
            Awaitable[int],
            self.redis.hincrby(key, "failures", 1),
        )
        if failures >= settings.MODEL_ROUTER_CIRCUIT_FAILURE_THRESHOLD:
            open_until = datetime.now(UTC) + timedelta(
                seconds=settings.MODEL_ROUTER_CIRCUIT_COOLDOWN_SECONDS
            )
            await cast(
                Awaitable[Any],
                self.redis.hset(key, mapping={"open_until": open_until.timestamp()}),
            )
        await self.redis.expire(
            key,
            settings.MODEL_ROUTER_CIRCUIT_COOLDOWN_SECONDS * 2,
        )


def routing_reason(context: RoutingContext) -> RoutingReason:
    if context.validation_failed:
        return RoutingReason.VALIDATION_RETRY
    if context.policy_requires_strong:
        return RoutingReason.POLICY
    if (
        context.retrieval_score is not None
        and context.retrieval_score < settings.MODEL_ROUTER_WEAK_RETRIEVAL_SCORE
    ):
        return RoutingReason.WEAK_RETRIEVAL
    if context.complexity_score >= settings.MODEL_ROUTER_COMPLEXITY_THRESHOLD:
        return RoutingReason.COMPLEX_QUERY
    return RoutingReason.DEFAULT


class ModelRouter:
    def __init__(
        self,
        targets: list[ModelTarget],
        circuit_store: CircuitStore,
        *,
        max_retries_per_target: int | None = None,
        retry_base_seconds: float | None = None,
        total_timeout_seconds: float | None = None,
    ) -> None:
        if not targets:
            raise ValueError("At least one model target is required")
        self.targets = targets
        self.circuits = circuit_store
        self.max_retries = (
            settings.MODEL_ROUTER_MAX_RETRIES_PER_TARGET
            if max_retries_per_target is None
            else max_retries_per_target
        )
        self.retry_base_seconds = (
            settings.MODEL_ROUTER_RETRY_BASE_SECONDS
            if retry_base_seconds is None
            else retry_base_seconds
        )
        self.total_timeout_seconds = (
            settings.MODEL_ROUTER_TOTAL_TIMEOUT_SECONDS
            if total_timeout_seconds is None
            else total_timeout_seconds
        )

    def _ordered_targets(self, context: RoutingContext) -> tuple[list[ModelTarget], RoutingReason]:
        reason = routing_reason(context)
        preferred = ModelTier.LOW_COST if reason is RoutingReason.DEFAULT else ModelTier.STRONG
        ordered = [target for target in self.targets if target.tier is preferred]
        ordered.extend(target for target in self.targets if target.tier is not preferred)
        return ordered, reason

    async def generate(
        self,
        request: GenerationRequest,
        context: RoutingContext,
    ) -> RoutedGeneration:
        ordered, initial_reason = self._ordered_targets(context)
        attempts: list[RouteAttempt] = []
        started = time.monotonic()
        try:
            async with asyncio.timeout(self.total_timeout_seconds):
                for target_index, target in enumerate(ordered):
                    if not await self.circuits.is_available(target.key):
                        continue
                    for attempt in range(1, self.max_retries + 2):
                        try:
                            response = await target.provider.generate(request)
                        except ProviderError as exc:
                            attempts.append(RouteAttempt(target.key, attempt, exc.category))
                            if self._affects_circuit(exc):
                                await self.circuits.record_failure(target.key)
                            if exc.category is ProviderErrorCategory.INVALID_REQUEST:
                                raise
                            if not exc.retryable or attempt > self.max_retries:
                                break
                            await asyncio.sleep(self.retry_base_seconds * (2 ** (attempt - 1)))
                        else:
                            await self.circuits.record_success(target.key)
                            attempts.append(RouteAttempt(target.key, attempt))
                            selected_reason = (
                                RoutingReason.PROVIDER_FAILOVER
                                if target_index > 0
                                else initial_reason
                            )
                            return RoutedGeneration(
                                response=response,
                                target=target,
                                routing_reason=selected_reason,
                                initial_reason=initial_reason,
                                attempts=attempts,
                            )
        except TimeoutError:
            pass
        elapsed_ms = int((time.monotonic() - started) * 1000)
        raise AllProvidersUnavailableError(
            f"No configured AI provider completed within the request budget ({elapsed_ms} ms)"
        )

    async def stream(
        self,
        request: GenerationRequest,
        context: RoutingContext,
    ) -> AsyncIterator[RoutedStreamEvent]:
        ordered, initial_reason = self._ordered_targets(context)
        try:
            async with asyncio.timeout(self.total_timeout_seconds):
                for target_index, target in enumerate(ordered):
                    if not await self.circuits.is_available(target.key):
                        continue
                    for attempt in range(1, self.max_retries + 2):
                        emitted = False
                        try:
                            async for event in target.provider.stream(request):
                                emitted = emitted or bool(event.text)
                                selected_reason = (
                                    RoutingReason.PROVIDER_FAILOVER
                                    if target_index > 0
                                    else initial_reason
                                )
                                yield RoutedStreamEvent(
                                    event=event,
                                    target=target,
                                    routing_reason=selected_reason,
                                    initial_reason=initial_reason,
                                    attempt=attempt,
                                )
                            await self.circuits.record_success(target.key)
                            return
                        except ProviderError as exc:
                            if self._affects_circuit(exc):
                                await self.circuits.record_failure(target.key)
                            if emitted or exc.category is ProviderErrorCategory.INVALID_REQUEST:
                                raise
                            if not exc.retryable or attempt > self.max_retries:
                                break
                            await asyncio.sleep(self.retry_base_seconds * (2 ** (attempt - 1)))
        except TimeoutError:
            pass
        raise AllProvidersUnavailableError("No configured AI provider completed the stream")

    @staticmethod
    def _affects_circuit(error: ProviderError) -> bool:
        return error.retryable or error.category in {
            ProviderErrorCategory.AUTHENTICATION,
            ProviderErrorCategory.FATAL,
            ProviderErrorCategory.INVALID_RESPONSE,
        }

    async def aclose(self) -> None:
        seen: set[int] = set()
        for target in self.targets:
            provider_id = id(target.provider)
            if provider_id in seen:
                continue
            seen.add(provider_id)
            close = getattr(target.provider, "aclose", None)
            if close is not None:
                await close()


__all__ = [
    "AllProvidersUnavailableError",
    "CircuitStore",
    "InMemoryCircuitStore",
    "ModelRouter",
    "ModelTarget",
    "ModelTier",
    "RedisCircuitStore",
    "RouteAttempt",
    "RoutedGeneration",
    "RoutedStreamEvent",
    "RoutingContext",
    "RoutingReason",
    "routing_reason",
]
