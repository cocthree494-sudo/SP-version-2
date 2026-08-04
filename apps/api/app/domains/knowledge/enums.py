"""Stable persisted states for knowledge ingestion."""

from enum import StrEnum


class KnowledgeSourceType(StrEnum):
    FILE = "file"
    WEBSITE = "website"
    MANUAL = "manual"


class KnowledgeSourceStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    DELETING = "deleting"


class DocumentStatus(StrEnum):
    STAGED = "staged"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    FAILED = "failed"


class IngestionJobType(StrEnum):
    INGEST_SOURCE = "ingest_source"
    DELETE_SOURCE = "delete_source"


class IngestionJobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    RETRY_SCHEDULED = "retry_scheduled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_JOB_STATES = frozenset(
    {
        IngestionJobState.SUCCEEDED,
        IngestionJobState.FAILED,
        IngestionJobState.CANCELLED,
    }
)


__all__ = [
    "TERMINAL_JOB_STATES",
    "DocumentStatus",
    "IngestionJobState",
    "IngestionJobType",
    "KnowledgeSourceStatus",
    "KnowledgeSourceType",
]
