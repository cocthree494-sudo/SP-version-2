"""Alembic comparison rules for database-owned generated infrastructure."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import JSON

_POSTGRES_JSON_CAST = re.compile(r"::jsonb?\s*$", re.IGNORECASE)


def _normalize_json_default(value: str) -> str:
    normalized = value.strip()
    while normalized.startswith("(") and normalized.endswith(")"):
        normalized = normalized[1:-1].strip()
    normalized = _POSTGRES_JSON_CAST.sub("", normalized).strip()
    if len(normalized) >= 2 and normalized.startswith("'") and normalized.endswith("'"):
        normalized = normalized[1:-1].replace("''", "'")
    return normalized


def compare_server_default(
    context: Any,
    inspected_column: Any,
    metadata_column: Any,
    inspected_default: str | None,
    metadata_default: Any,
    rendered_metadata_default: str | None,
) -> bool | None:
    """Compare JSON defaults without PostgreSQL's unsupported JSON equality.

    Alembic's PostgreSQL comparator executes ``database_default = model_default``.
    The ``json`` type intentionally has no equality operator, so compare its rendered
    expressions after removing PostgreSQL's reflection-only cast. Other column types
    continue through Alembic's dialect-specific comparison.
    """

    del context, inspected_column, metadata_default
    if not isinstance(metadata_column.type, JSON):
        return None
    if inspected_default is None or rendered_metadata_default is None:
        return inspected_default != rendered_metadata_default
    return _normalize_json_default(inspected_default) != _normalize_json_default(
        rendered_metadata_default
    )


def include_object(
    object_: Any,
    name: str,
    type_: str,
    reflected: bool,
    compare_to: Any,
) -> bool:
    """Exclude the PostgreSQL-only generated lexical column from model drift.

    ``document_chunks.search_vector`` and its GIN index are deliberately
    created by migration ``0007`` because generated full-text search is a PostgreSQL
    features. The ORM uses the column through a literal expression, while all
    application-owned columns remain part of the normal autogenerate diff.
    """

    del object_, compare_to
    return not (
        reflected
        and (
            (type_ == "column" and name == "search_vector")
            or (type_ == "index" and name == "ix_document_chunks_search_vector")
        )
    )


__all__ = ["compare_server_default", "include_object"]
