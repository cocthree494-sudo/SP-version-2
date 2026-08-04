"""Normalized provider request, response, usage, stream, and error types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ProviderErrorCategory(StrEnum):
    TIMEOUT = "timeout"
    THROTTLED = "throttled"
    UNAVAILABLE = "unavailable"
    AUTHENTICATION = "authentication"
    INVALID_REQUEST = "invalid_request"
    INVALID_RESPONSE = "invalid_response"
    FATAL = "fatal"


_RETRYABLE_CATEGORIES = {
    ProviderErrorCategory.TIMEOUT,
    ProviderErrorCategory.THROTTLED,
    ProviderErrorCategory.UNAVAILABLE,
}


class ProviderError(RuntimeError):
    """Secret-safe normalized provider error exposed to routers."""

    def __init__(
        self,
        category: ProviderErrorCategory,
        public_message: str,
        *,
        provider_id: str,
        status_code: int | None = None,
    ) -> None:
        super().__init__(public_message)
        self.category = category
        self.public_message = public_message
        self.provider_id = provider_id
        self.status_code = status_code

    @property
    def retryable(self) -> bool:
        return self.category in _RETRYABLE_CATEGORIES

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(category={self.category.value!r}, "
            f"provider_id={self.provider_id!r}, status_code={self.status_code!r})"
        )


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class StreamEventType(StrEnum):
    TEXT_DELTA = "text_delta"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class ProviderUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: MessageRole
    content: str


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    messages: list[ChatMessage]
    max_output_tokens: int = 800
    temperature: float = 0.0
    stop: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GenerationResponse:
    text: str
    finish_reason: str | None
    usage: ProviderUsage
    provider_id: str
    model_id: str


@dataclass(frozen=True, slots=True)
class StreamEvent:
    type: StreamEventType
    text: str = ""
    finish_reason: str | None = None
    usage: ProviderUsage | None = None


__all__ = [
    "ChatMessage",
    "GenerationRequest",
    "GenerationResponse",
    "MessageRole",
    "ProviderError",
    "ProviderErrorCategory",
    "ProviderUsage",
    "StreamEvent",
    "StreamEventType",
]
