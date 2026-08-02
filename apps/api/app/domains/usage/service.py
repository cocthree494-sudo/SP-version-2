"""Transaction-composable usage recording and read-only summaries."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.bots.repositories import BotRepository
from app.domains.usage.models import UsageEvent
from app.domains.usage.repositories import UsageRepository
from app.domains.usage.schemas import UsageRecordInput, UsageSummaryResponse


class UsageDomainError(RuntimeError):
    """Base class for expected usage-domain failures."""


class UsageBotNotFoundError(UsageDomainError):
    """Raised when an event names a bot outside the recording tenant."""


class UsageRangeError(UsageDomainError):
    """Raised for an invalid summary time range."""


def _normalize_boundary(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise UsageRangeError("Usage summary boundaries must include a timezone")
    return value.astimezone(UTC)


class UsageService:
    """Record immutable events and aggregate a tenant's usage."""

    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.repository = UsageRepository(session, tenant_id)

    async def record(self, payload: UsageRecordInput) -> UsageEvent:
        if payload.bot_id is not None:
            bot = await BotRepository(self.session, self.tenant_id).get(payload.bot_id)
            if bot is None:
                raise UsageBotNotFoundError("Bot not found in usage-event tenant")
        # Deliberately flush without committing so message persistence and
        # usage accounting can share one atomic orchestrator transaction.
        return await self.repository.record(payload)

    async def summarize(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        bot_id: UUID | None = None,
    ) -> UsageSummaryResponse:
        normalized_start = _normalize_boundary(start)
        normalized_end = _normalize_boundary(end)
        if (
            normalized_start is not None
            and normalized_end is not None
            and normalized_start >= normalized_end
        ):
            raise UsageRangeError("Usage summary start must be before end")
        return await self.repository.summarize(
            start=normalized_start,
            end=normalized_end,
            bot_id=bot_id,
        )


__all__ = [
    "UsageBotNotFoundError",
    "UsageDomainError",
    "UsageRangeError",
    "UsageService",
]
