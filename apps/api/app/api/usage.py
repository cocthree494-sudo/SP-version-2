"""Read-only tenant usage summary API."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import CurrentAuth
from app.db.session import get_db_session
from app.domains.usage.schemas import UsageSummaryResponse
from app.domains.usage.service import UsageRangeError, UsageService

router = APIRouter(prefix="/v1/usage", tags=["usage"])
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/summary", response_model=UsageSummaryResponse)
async def usage_summary(
    session: DbSession,
    context: CurrentAuth,
    start: Annotated[datetime | None, Query()] = None,
    end: Annotated[datetime | None, Query()] = None,
    bot_id: Annotated[UUID | None, Query()] = None,
) -> UsageSummaryResponse:
    try:
        return await UsageService(session, context.tenant.id).summarize(
            start=start,
            end=end,
            bot_id=bot_id,
        )
    except UsageRangeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from None


__all__ = ["router"]
