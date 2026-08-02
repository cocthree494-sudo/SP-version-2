"""Stable categories for normalized provider usage."""

from enum import StrEnum


class UsageOperation(StrEnum):
    """Provider-neutral operation that incurred usage."""

    GENERATION = "generation"
    EMBEDDING = "embedding"


__all__ = ["UsageOperation"]
