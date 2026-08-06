"""Public widget session and chat request contracts."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WidgetSessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_token: str
    token_type: Literal["bearer"] = Field(default="bearer")
    expires_in: int
    expires_at: datetime
    conversation_id: UUID


class WidgetMessageRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    message: str = Field(min_length=1, max_length=20_000)


class PlaygroundSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bot_id: UUID


class PlaygroundSessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: UUID


__all__ = [
    "PlaygroundSessionRequest",
    "PlaygroundSessionResponse",
    "WidgetMessageRequest",
    "WidgetSessionResponse",
]
