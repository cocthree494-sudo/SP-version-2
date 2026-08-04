"""Deterministic structural text chunking with bounded token overlap."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import settings
from app.providers.embeddings import estimate_tokens

_TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", flags=re.UNICODE)
_HEADING_PATTERN = re.compile(r"(?m)^#{1,6}\s+(.+?)\s*$")


@dataclass(frozen=True, slots=True)
class TextChunk:
    ordinal: int
    content: str
    token_count: int
    start_char: int
    end_char: int
    section: str | None


def _section_at(text: str, offset: int) -> str | None:
    section = None
    for heading in _HEADING_PATTERN.finditer(text):
        if heading.start() > offset:
            break
        section = " ".join(heading.group(1).split())[:300]
    return section


def chunk_text(
    text: str,
    *,
    max_tokens: int | None = None,
    overlap_tokens: int | None = None,
) -> list[TextChunk]:
    limit = settings.CHUNK_MAX_TOKENS if max_tokens is None else max_tokens
    overlap = settings.CHUNK_OVERLAP_TOKENS if overlap_tokens is None else overlap_tokens
    if limit <= 0 or overlap < 0 or overlap >= limit:
        raise ValueError("Chunk limits require 0 <= overlap_tokens < max_tokens")
    tokens = list(_TOKEN_PATTERN.finditer(text))
    if not tokens:
        return []

    chunks: list[TextChunk] = []
    start_index = 0
    while start_index < len(tokens):
        end_index = min(start_index + limit, len(tokens))
        if end_index < len(tokens):
            minimum_boundary = start_index + max(limit // 2, 1)
            candidate_end = end_index
            for index in range(end_index - 1, minimum_boundary - 1, -1):
                gap_start = tokens[index - 1].end()
                gap_end = tokens[index].start()
                if "\n\n" in text[gap_start:gap_end]:
                    candidate_end = index
                    break
            end_index = candidate_end

        raw_start = tokens[start_index].start()
        raw_end = tokens[end_index - 1].end()
        content = text[raw_start:raw_end].strip()
        if content:
            leading = len(text[raw_start:raw_end]) - len(text[raw_start:raw_end].lstrip())
            trailing = len(text[raw_start:raw_end]) - len(text[raw_start:raw_end].rstrip())
            start_char = raw_start + leading
            end_char = raw_end - trailing
            chunks.append(
                TextChunk(
                    ordinal=len(chunks),
                    content=content,
                    token_count=estimate_tokens(content),
                    start_char=start_char,
                    end_char=end_char,
                    section=_section_at(text, start_char),
                )
            )
        if end_index >= len(tokens):
            break
        next_start = end_index - overlap
        if next_start <= start_index:
            next_start = start_index + 1
        start_index = next_start
    return chunks


__all__ = ["TextChunk", "chunk_text"]
