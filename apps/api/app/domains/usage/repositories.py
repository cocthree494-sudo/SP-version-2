"""Fail-closed append-only usage persistence and aggregation."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import (
    TenantContextError,
    get_current_tenant_id,
    maybe_current_tenant_id,
    set_database_tenant,
)
from app.domains.usage.models import UsageEvent
from app.domains.usage.schemas import (
    UsageBreakdownResponse,
    UsageRecordInput,
    UsageSummaryResponse,
)


class UsageRepository:
    """Append events and summarize exactly one tenant's immutable history."""

    def __init__(self, session: AsyncSession, tenant_id: UUID | None = None) -> None:
        self.session = session
        self._tenant_id = tenant_id

    def _resolve_tenant_id(self) -> UUID:
        context_tenant_id = maybe_current_tenant_id()
        if self._tenant_id is not None:
            if context_tenant_id is not None and context_tenant_id != self._tenant_id:
                raise TenantContextError("Repository tenant does not match active tenant context")
            return self._tenant_id
        return get_current_tenant_id()

    async def _prepare_scope(self) -> UUID:
        tenant_id = self._resolve_tenant_id()
        await set_database_tenant(self.session, tenant_id)
        return tenant_id

    async def record(self, payload: UsageRecordInput) -> UsageEvent:
        tenant_id = await self._prepare_scope()
        values = payload.model_dump(exclude={"created_at"})
        event = UsageEvent(tenant_id=tenant_id, **values)
        if payload.created_at is not None:
            event.created_at = payload.created_at
        self.session.add(event)
        await self.session.flush()
        return event

    async def summarize(
        self,
        *,
        start: datetime | None,
        end: datetime | None,
        bot_id: UUID | None,
    ) -> UsageSummaryResponse:
        tenant_id = await self._prepare_scope()
        filters = [UsageEvent.tenant_id == tenant_id]
        if start is not None:
            filters.append(UsageEvent.created_at >= start)
        if end is not None:
            filters.append(UsageEvent.created_at < end)
        if bot_id is not None:
            filters.append(UsageEvent.bot_id == bot_id)

        totals = (
            await self.session.execute(
                select(
                    func.count(UsageEvent.id),
                    func.coalesce(func.sum(UsageEvent.input_tokens), 0),
                    func.coalesce(func.sum(UsageEvent.output_tokens), 0),
                    func.coalesce(func.sum(UsageEvent.cache_read_tokens), 0),
                    func.coalesce(func.sum(UsageEvent.cache_write_tokens), 0),
                    func.coalesce(func.sum(UsageEvent.latency_ms), 0),
                    func.coalesce(func.avg(UsageEvent.latency_ms), 0.0),
                    func.coalesce(func.sum(UsageEvent.estimated_cost_microusd), 0),
                ).where(*filters)
            )
        ).one()

        breakdown_rows = (
            await self.session.execute(
                select(
                    UsageEvent.operation,
                    UsageEvent.provider,
                    UsageEvent.model,
                    func.count(UsageEvent.id),
                    func.coalesce(func.sum(UsageEvent.input_tokens), 0),
                    func.coalesce(func.sum(UsageEvent.output_tokens), 0),
                    func.coalesce(func.sum(UsageEvent.cache_read_tokens), 0),
                    func.coalesce(func.sum(UsageEvent.cache_write_tokens), 0),
                    func.coalesce(func.sum(UsageEvent.latency_ms), 0),
                    func.coalesce(func.sum(UsageEvent.estimated_cost_microusd), 0),
                )
                .where(*filters)
                .group_by(UsageEvent.operation, UsageEvent.provider, UsageEvent.model)
                .order_by(UsageEvent.provider, UsageEvent.model, UsageEvent.operation)
            )
        ).all()

        input_tokens = int(totals[1])
        output_tokens = int(totals[2])
        by_model = [
            UsageBreakdownResponse(
                operation=row[0],
                provider=row[1],
                model=row[2],
                event_count=int(row[3]),
                input_tokens=int(row[4]),
                output_tokens=int(row[5]),
                cache_read_tokens=int(row[6]),
                cache_write_tokens=int(row[7]),
                total_tokens=int(row[4]) + int(row[5]),
                total_latency_ms=int(row[8]),
                estimated_cost_microusd=int(row[9]),
            )
            for row in breakdown_rows
        ]
        return UsageSummaryResponse(
            start=start,
            end=end,
            bot_id=bot_id,
            event_count=int(totals[0]),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=int(totals[3]),
            cache_write_tokens=int(totals[4]),
            total_tokens=input_tokens + output_tokens,
            total_latency_ms=int(totals[5]),
            average_latency_ms=float(totals[6]),
            estimated_cost_microusd=int(totals[7]),
            by_model=by_model,
        )


__all__ = ["UsageRepository"]
