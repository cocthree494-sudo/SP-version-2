"""Provider-neutral embedding contract and deterministic local provider."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Protocol

from app.core.config import settings
from app.providers.types import ProviderError, ProviderErrorCategory


class EmbeddingProviderError(ProviderError):
    """Normalized provider failure without request payloads or credentials."""

    def __init__(
        self,
        category: ProviderErrorCategory,
        message: str,
        *,
        provider_id: str,
        status_code: int | None = None,
    ) -> None:
        super().__init__(
            category,
            message,
            provider_id=provider_id,
            status_code=status_code,
        )


@dataclass(frozen=True, slots=True)
class EmbeddingUsage:
    input_tokens: int


@dataclass(frozen=True, slots=True)
class EmbeddingBatch:
    embeddings: list[list[float]]
    usage: EmbeddingUsage


class EmbeddingProvider(Protocol):
    provider_id: str
    model_id: str
    dimensions: int

    async def embed(self, texts: list[str]) -> EmbeddingBatch: ...


def estimate_tokens(text: str) -> int:
    return len(re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE))


class DeterministicEmbeddingProvider:
    """Credential-free stable vectors for tests and local development."""

    def __init__(
        self,
        *,
        provider_id: str | None = None,
        model_id: str | None = None,
        dimensions: int | None = None,
    ) -> None:
        self.provider_id = provider_id or settings.EMBEDDING_PROVIDER_ID
        self.model_id = model_id or settings.EMBEDDING_MODEL_ID
        self.dimensions = dimensions or settings.EMBEDDING_DIMENSIONS

    def _vector(self, text: str) -> list[float]:
        values = [0.0] * self.dimensions
        tokens = re.findall(r"\w+|[^\w\s]", text.casefold(), flags=re.UNICODE)
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            values[index] += sign
        magnitude = math.sqrt(sum(value * value for value in values))
        if magnitude:
            values = [value / magnitude for value in values]
        return values

    async def embed(self, texts: list[str]) -> EmbeddingBatch:
        if not texts:
            return EmbeddingBatch(embeddings=[], usage=EmbeddingUsage(input_tokens=0))
        return EmbeddingBatch(
            embeddings=[self._vector(text) for text in texts],
            usage=EmbeddingUsage(input_tokens=sum(estimate_tokens(text) for text in texts)),
        )


__all__ = [
    "DeterministicEmbeddingProvider",
    "EmbeddingBatch",
    "EmbeddingProvider",
    "EmbeddingProviderError",
    "EmbeddingUsage",
    "estimate_tokens",
]
