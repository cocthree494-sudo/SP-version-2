"""Alembic comparison rules for database-owned generated infrastructure."""

from __future__ import annotations

from typing import Any


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


__all__ = ["include_object"]
