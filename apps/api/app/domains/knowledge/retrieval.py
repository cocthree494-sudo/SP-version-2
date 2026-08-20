"""Tenant-scoped hybrid vector/lexical retrieval with citation metadata."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.tenancy import set_database_tenant
from app.domains.knowledge.enums import DocumentStatus, KnowledgeSourceStatus
from app.domains.knowledge.models import Document, DocumentChunk, KnowledgeSource
from app.providers.embeddings import EmbeddingProvider, EmbeddingProviderError


class RetrievalError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class Citation:
    source_id: UUID
    document_id: UUID
    title: str | None
    canonical_url: str | None
    chunk_ordinal: int
    start_char: int
    end_char: int


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    chunk_id: UUID
    content: str
    score: float
    vector_score: float | None
    lexical_score: float | None
    citation: Citation
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _Candidate:
    chunk: DocumentChunk
    document: Document
    source: KnowledgeSource
    score: float


def _terms(value: str) -> set[str]:
    return set(re.findall(r"\w+", value.casefold(), flags=re.UNICODE))


_LEXICAL_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "does",
        "do",
        "for",
        "from",
        "how",
        "i",
        "in",
        "is",
        "it",
        "me",
        "of",
        "on",
        "or",
        "the",
        "their",
        "they",
        "this",
        "to",
        "we",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "with",
        "you",
        "your",
    }
)


def _lexical_terms(value: str) -> set[str]:
    """Remove conversational glue so lexical evidence identifies the subject."""

    return {term for term in _terms(value) if term not in _LEXICAL_STOPWORDS}


def _lexical_score(query: str, content: str) -> float:
    query_terms = _lexical_terms(query)
    if not query_terms:
        return 0.0
    content_terms = _terms(content)
    return len(query_terms & content_terms) / len(query_terms)


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


class HybridRetrievalService:
    """Fuse bounded PostgreSQL semantic and lexical candidate rankings."""

    def __init__(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.embedding_provider = embedding_provider

    def _base_filters(
        self,
        *,
        bot_id: UUID,
        source_ids: set[UUID] | None,
        language: str | None,
    ) -> list[Any]:
        filters: list[Any] = [
            DocumentChunk.tenant_id == self.tenant_id,
            Document.tenant_id == self.tenant_id,
            KnowledgeSource.tenant_id == self.tenant_id,
            KnowledgeSource.bot_id == bot_id,
            Document.status == DocumentStatus.ACTIVE,
            KnowledgeSource.status.in_(
                [
                    KnowledgeSourceStatus.READY,
                    KnowledgeSourceStatus.PROCESSING,
                    KnowledgeSourceStatus.FAILED,
                ]
            ),
        ]
        if source_ids:
            filters.append(KnowledgeSource.id.in_(source_ids))
        if language:
            filters.append(DocumentChunk.chunk_metadata["language"].as_string() == language)
        return filters

    def _base_query(self, filters: list[Any]):
        return (
            select(DocumentChunk, Document, KnowledgeSource)
            .join(
                Document,
                (Document.id == DocumentChunk.document_id)
                & (Document.tenant_id == DocumentChunk.tenant_id),
            )
            .join(
                KnowledgeSource,
                (KnowledgeSource.id == Document.source_id)
                & (KnowledgeSource.tenant_id == Document.tenant_id),
            )
            .where(*filters)
        )

    async def retrieve(
        self,
        *,
        bot_id: UUID,
        query: str,
        top_k: int = 6,
        source_ids: set[UUID] | None = None,
        language: str | None = None,
    ) -> list[RetrievalResult]:
        normalized_query = query.strip()
        if not normalized_query:
            return []
        if not 1 <= top_k <= 50:
            raise ValueError("top_k must be between 1 and 50")
        try:
            embedded = await self.embedding_provider.embed([normalized_query])
        except EmbeddingProviderError as exc:
            raise RetrievalError(
                exc.category.value,
                str(exc),
                retryable=exc.retryable,
            ) from exc
        if len(embedded.embeddings) != 1:
            raise RetrievalError(
                "invalid_embedding_response",
                "Embedding provider returned an invalid query vector",
                retryable=False,
            )
        query_vector = embedded.embeddings[0]
        await set_database_tenant(self.session, self.tenant_id)
        filters = self._base_filters(
            bot_id=bot_id,
            source_ids=source_ids,
            language=language,
        )
        if self.session.get_bind().dialect.name == "postgresql":
            vector_candidates, lexical_candidates = await self._postgres_candidates(
                filters,
                normalized_query,
                query_vector,
            )
        else:
            vector_candidates, lexical_candidates = await self._portable_candidates(
                filters,
                normalized_query,
                query_vector,
            )
        return self._fuse(vector_candidates, lexical_candidates, top_k=top_k)

    async def _postgres_candidates(
        self,
        filters: list[Any],
        query: str,
        query_vector: list[float],
    ) -> tuple[list[_Candidate], list[_Candidate]]:
        distance = DocumentChunk.embedding.cosine_distance(query_vector)
        vector_rows = (
            await self.session.execute(
                self._base_query(filters)
                .add_columns((1.0 - distance).label("semantic_score"))
                .order_by(distance)
                .limit(settings.RETRIEVAL_CANDIDATE_LIMIT)
            )
        ).all()
        query_terms = sorted(_lexical_terms(query))
        lexical_rows: Sequence[Any] = ()
        if query_terms:
            ts_query: Any = func.plainto_tsquery("simple", query_terms[0])
            for term in query_terms[1:]:
                ts_query = ts_query.op("||")(func.plainto_tsquery("simple", term))
            search_vector: Any = literal_column("document_chunks.search_vector")
            rank = func.ts_rank_cd(search_vector, ts_query)
            lexical_rows = (
                await self.session.execute(
                    self._base_query(filters)
                    .add_columns(rank.label("lexical_score"))
                    .where(search_vector.op("@@")(ts_query))
                    .order_by(rank.desc())
                    .limit(settings.RETRIEVAL_CANDIDATE_LIMIT)
                )
            ).all()
        return (
            [_Candidate(row[0], row[1], row[2], float(row[3])) for row in vector_rows],
            [_Candidate(row[0], row[1], row[2], float(row[3])) for row in lexical_rows],
        )

    async def _portable_candidates(
        self,
        filters: list[Any],
        query: str,
        query_vector: list[float],
    ) -> tuple[list[_Candidate], list[_Candidate]]:
        rows = (await self.session.execute(self._base_query(filters).limit(2000))).all()
        vector_candidates = sorted(
            (
                _Candidate(
                    row[0],
                    row[1],
                    row[2],
                    _cosine_similarity(list(row[0].embedding), query_vector),
                )
                for row in rows
            ),
            key=lambda candidate: candidate.score,
            reverse=True,
        )[: settings.RETRIEVAL_CANDIDATE_LIMIT]
        lexical_candidates = sorted(
            (
                _Candidate(row[0], row[1], row[2], _lexical_score(query, row[0].content))
                for row in rows
            ),
            key=lambda candidate: candidate.score,
            reverse=True,
        )
        lexical_candidates = [
            candidate
            for candidate in lexical_candidates[: settings.RETRIEVAL_CANDIDATE_LIMIT]
            if candidate.score > 0
        ]
        return vector_candidates, lexical_candidates

    def _fuse(
        self,
        vector_candidates: list[_Candidate],
        lexical_candidates: list[_Candidate],
        *,
        top_k: int,
    ) -> list[RetrievalResult]:
        # When lexical evidence identifies one or more sources, do not let
        # unrelated semantic neighbours from another source pollute the
        # grounded prompt. If lexical search finds nothing, retain the full
        # semantic candidate set for natural-language queries.
        lexical_source_ids = {candidate.source.id for candidate in lexical_candidates}
        if lexical_source_ids:
            vector_candidates = [
                candidate
                for candidate in vector_candidates
                if candidate.source.id in lexical_source_ids
            ]

        candidates: dict[UUID, _Candidate] = {}
        fused: dict[UUID, float] = {}
        vector_scores: dict[UUID, float] = {}
        lexical_scores: dict[UUID, float] = {}
        for rank, candidate in enumerate(vector_candidates, start=1):
            candidates[candidate.chunk.id] = candidate
            vector_scores[candidate.chunk.id] = candidate.score
            fused[candidate.chunk.id] = fused.get(candidate.chunk.id, 0.0) + (
                settings.RETRIEVAL_VECTOR_WEIGHT / (settings.RETRIEVAL_RRF_K + rank)
            )
        for rank, candidate in enumerate(lexical_candidates, start=1):
            candidates[candidate.chunk.id] = candidate
            lexical_scores[candidate.chunk.id] = candidate.score
            fused[candidate.chunk.id] = fused.get(candidate.chunk.id, 0.0) + (
                settings.RETRIEVAL_LEXICAL_WEIGHT / (settings.RETRIEVAL_RRF_K + rank)
            )

        ranked_ids = sorted(fused, key=lambda chunk_id: fused[chunk_id], reverse=True)
        results: list[RetrievalResult] = []
        seen_checksums: set[str] = set()
        for chunk_id in ranked_ids:
            candidate = candidates[chunk_id]
            if candidate.chunk.content_checksum_sha256 in seen_checksums:
                continue
            seen_checksums.add(candidate.chunk.content_checksum_sha256)
            results.append(
                RetrievalResult(
                    chunk_id=chunk_id,
                    content=candidate.chunk.content,
                    score=fused[chunk_id],
                    vector_score=vector_scores.get(chunk_id),
                    lexical_score=lexical_scores.get(chunk_id),
                    citation=Citation(
                        source_id=candidate.source.id,
                        document_id=candidate.document.id,
                        title=candidate.document.title,
                        canonical_url=candidate.document.canonical_url,
                        chunk_ordinal=candidate.chunk.ordinal,
                        start_char=candidate.chunk.start_char,
                        end_char=candidate.chunk.end_char,
                    ),
                    metadata=dict(candidate.chunk.chunk_metadata),
                )
            )
            if len(results) >= top_k:
                break
        return results


__all__ = ["Citation", "HybridRetrievalService", "RetrievalError", "RetrievalResult"]
