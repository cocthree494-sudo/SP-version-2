"""Tenant-addressed Redis rate limiting for public chat boundaries."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any, Protocol, cast
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

_FIXED_WINDOW_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
return {count, ttl}
"""


class RateLimiterUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after_seconds: int


class RateLimiter(Protocol):
    async def consume(
        self,
        *,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision: ...


def public_rate_limit_key(
    *,
    tenant_id: UUID,
    bot_id: UUID,
    scope: str,
    identity: str,
) -> str:
    """Hash client identity while retaining explicit tenant/bot cache scope."""

    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"rate-limit:{tenant_id}:{bot_id}:{scope}:{digest}"


class RedisRateLimiter:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def consume(
        self,
        *,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        try:
            raw = await cast(
                Awaitable[Any],
                self.redis.eval(_FIXED_WINDOW_SCRIPT, 1, key, str(window_seconds)),
            )
            values = cast(list[Any], raw)
            count = int(values[0])
            ttl = max(1, int(values[1]))
        except (RedisError, TypeError, ValueError, IndexError) as exc:
            raise RateLimiterUnavailableError("Public chat rate limiter is unavailable") from exc
        return RateLimitDecision(
            allowed=count <= limit,
            remaining=max(0, limit - count),
            retry_after_seconds=ttl,
        )


@dataclass(slots=True)
class _MemoryWindow:
    count: int
    expires_at: float


class InMemoryRateLimiter:
    """Deterministic process-local test implementation of the Redis contract."""

    def __init__(self) -> None:
        self._windows: dict[str, _MemoryWindow] = {}

    async def consume(
        self,
        *,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        now = time.monotonic()
        window = self._windows.get(key)
        if window is None or window.expires_at <= now:
            window = _MemoryWindow(count=0, expires_at=now + window_seconds)
            self._windows[key] = window
        window.count += 1
        return RateLimitDecision(
            allowed=window.count <= limit,
            remaining=max(0, limit - window.count),
            retry_after_seconds=max(1, int(window.expires_at - now)),
        )


__all__ = [
    "InMemoryRateLimiter",
    "RateLimitDecision",
    "RateLimiter",
    "RateLimiterUnavailableError",
    "RedisRateLimiter",
    "public_rate_limit_key",
]
