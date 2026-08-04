"""Provider-neutral LLM protocol and deterministic implementation."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from app.core.config import settings
from app.providers.embeddings import estimate_tokens
from app.providers.types import (
    GenerationRequest,
    GenerationResponse,
    ProviderUsage,
    StreamEvent,
    StreamEventType,
)


class LLMProvider(Protocol):
    provider_id: str
    model_id: str

    async def generate(self, request: GenerationRequest) -> GenerationResponse: ...

    def stream(self, request: GenerationRequest) -> AsyncIterator[StreamEvent]: ...


class DeterministicLLMProvider:
    """Credential-free stable generation for local work and unit tests."""

    def __init__(
        self,
        *,
        provider_id: str | None = None,
        model_id: str | None = None,
        response_text: str | None = None,
        stream_chunk_chars: int = 16,
    ) -> None:
        self.provider_id = provider_id or settings.AI_PROVIDER_ID
        self.model_id = model_id or settings.LLM_MODEL_ID
        self.response_text = response_text or settings.DETERMINISTIC_LLM_RESPONSE
        self.stream_chunk_chars = stream_chunk_chars

    def _usage(self, request: GenerationRequest) -> ProviderUsage:
        return ProviderUsage(
            input_tokens=sum(estimate_tokens(message.content) for message in request.messages),
            output_tokens=estimate_tokens(self.response_text),
        )

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        return GenerationResponse(
            text=self.response_text,
            finish_reason="stop",
            usage=self._usage(request),
            provider_id=self.provider_id,
            model_id=self.model_id,
        )

    async def stream(self, request: GenerationRequest) -> AsyncIterator[StreamEvent]:
        for start in range(0, len(self.response_text), self.stream_chunk_chars):
            yield StreamEvent(
                type=StreamEventType.TEXT_DELTA,
                text=self.response_text[start : start + self.stream_chunk_chars],
            )
        yield StreamEvent(
            type=StreamEventType.COMPLETED,
            finish_reason="stop",
            usage=self._usage(request),
        )


__all__ = ["DeterministicLLMProvider", "LLMProvider"]
