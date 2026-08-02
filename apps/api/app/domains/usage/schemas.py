"""Provider-neutral usage recording and summary contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domains.usage.enums import UsageOperation


class UsageRecordInput(BaseModel):
    """Normalized values accepted from an internal provider adapter."""

    model_config = ConfigDict(str_strip_whitespace=True)

    bot_id: UUID | None = None
    conversation_id: UUID | None = None
    operation: UsageOperation
    provider: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=200)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cache_read_tokens: int = Field(default=0, ge=0)
    cache_write_tokens: int = Field(default=0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    estimated_cost_microusd: int = Field(default=0, ge=0)
    created_at: datetime | None = None

    @field_validator("provider")
    @classmethod
    def normalize_provider(cls, value: str) -> str:
        return value.casefold()

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must include a timezone")
        return value.astimezone(UTC)


class UsageBreakdownResponse(BaseModel):
    operation: UsageOperation
    provider: str
    model: str
    event_count: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    total_tokens: int
    total_latency_ms: int
    estimated_cost_microusd: int


class UsageSummaryResponse(BaseModel):
    start: datetime | None
    end: datetime | None
    bot_id: UUID | None
    event_count: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    total_tokens: int
    total_latency_ms: int
    average_latency_ms: float
    estimated_cost_microusd: int
    by_model: list[UsageBreakdownResponse]


__all__ = ["UsageBreakdownResponse", "UsageRecordInput", "UsageSummaryResponse"]
