"""Chunk, embed in batches, and persist a staged document version."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domains.knowledge.chunking import TextChunk, chunk_text
from app.domains.knowledge.models import Document
from app.domains.knowledge.repositories import DocumentChunkRepository
from app.providers.embeddings import EmbeddingProvider, EmbeddingProviderError


class EmbeddingPipelineError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class EmbeddingPipelineResult:
    chunk_count: int
    input_tokens: int


class EmbeddingPipeline:
    """Provider-neutral, transaction-composable document embedding pipeline."""

    def __init__(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        provider: EmbeddingProvider,
    ) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.provider = provider
        self.chunks = DocumentChunkRepository(session, tenant_id)

    async def run(self, document: Document, text: str) -> EmbeddingPipelineResult:
        chunks = chunk_text(text)
        if not chunks:
            raise EmbeddingPipelineError(
                "empty_document",
                "No useful text was available for embedding",
                retryable=False,
            )
        total_input_tokens = 0
        for start in range(0, len(chunks), settings.EMBEDDING_BATCH_SIZE):
            batch_chunks = chunks[start : start + settings.EMBEDDING_BATCH_SIZE]
            try:
                response = await self.provider.embed([chunk.content for chunk in batch_chunks])
            except EmbeddingProviderError as exc:
                raise EmbeddingPipelineError(
                    exc.category.value,
                    str(exc),
                    retryable=exc.retryable,
                ) from exc
            if len(response.embeddings) != len(batch_chunks):
                raise EmbeddingPipelineError(
                    "invalid_embedding_response",
                    "Embedding provider returned an invalid item count",
                    retryable=False,
                )
            records: list[dict[str, Any]] = []
            for chunk, embedding in zip(batch_chunks, response.embeddings, strict=True):
                if len(embedding) != self.provider.dimensions:
                    raise EmbeddingPipelineError(
                        "invalid_embedding_dimensions",
                        "Embedding provider returned invalid dimensions",
                        retryable=False,
                    )
                records.append(self._record_values(chunk, embedding))
            await self.chunks.create_batch(document=document, chunks=records)
            total_input_tokens += response.usage.input_tokens
        return EmbeddingPipelineResult(
            chunk_count=len(chunks),
            input_tokens=total_input_tokens,
        )

    def _record_values(self, chunk: TextChunk, embedding: list[float]) -> dict[str, Any]:
        return {
            "ordinal": chunk.ordinal,
            "content": chunk.content,
            "content_checksum_sha256": hashlib.sha256(
                chunk.content.encode("utf-8")
            ).hexdigest(),
            "token_count": chunk.token_count,
            "start_char": chunk.start_char,
            "end_char": chunk.end_char,
            "embedding": embedding,
            "embedding_provider": self.provider.provider_id,
            "embedding_model": self.provider.model_id,
            "chunk_metadata": {"section": chunk.section} if chunk.section else {},
        }


__all__ = ["EmbeddingPipeline", "EmbeddingPipelineError", "EmbeddingPipelineResult"]
