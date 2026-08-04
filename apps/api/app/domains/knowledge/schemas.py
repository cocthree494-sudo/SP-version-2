"""Authenticated knowledge-source request and response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import settings
from app.domains.knowledge.crawler import canonicalize_url
from app.domains.knowledge.enums import KnowledgeSourceStatus, KnowledgeSourceType
from app.domains.knowledge.models import KnowledgeSource


class KnowledgeSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    bot_id: UUID
    type: KnowledgeSourceType
    name: str
    status: KnowledgeSourceStatus
    details: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class WebsiteSourceCreateRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    max_pages: int = Field(default=20, ge=1, le=settings.WEBSITE_CRAWL_MAX_PAGES)
    max_depth: int = Field(default=2, ge=0, le=settings.WEBSITE_CRAWL_MAX_DEPTH)
    request_delay_seconds: float = Field(
        default=settings.WEBSITE_CRAWL_REQUEST_DELAY_SECONDS,
        ge=0.0,
        le=10.0,
    )

    @field_validator("url")
    @classmethod
    def normalize_url(cls, value: str) -> str:
        return canonicalize_url(value)

    @field_validator("name")
    @classmethod
    def strip_optional_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("Name cannot be blank")
        return stripped


class ManualSourceCreateRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1, max_length=20000)
    name: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("question", "answer", "name")
    @classmethod
    def strip_content(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("Content cannot be blank")
        return stripped


class ManualSourceUpdateRequest(BaseModel):
    question: str | None = Field(default=None, min_length=1, max_length=2000)
    answer: str | None = Field(default=None, min_length=1, max_length=20000)
    name: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("question", "answer", "name")
    @classmethod
    def strip_optional_content(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("Content cannot be blank")
        return stripped


_VISIBLE_DETAILS: dict[KnowledgeSourceType, frozenset[str]] = {
    KnowledgeSourceType.FILE: frozenset(
        {
            "original_filename",
            "file_kind",
            "media_type",
            "size_bytes",
            "checksum_sha256",
        }
    ),
    KnowledgeSourceType.WEBSITE: frozenset(
        {"start_url", "max_pages", "max_depth", "request_delay_seconds"}
    ),
    KnowledgeSourceType.MANUAL: frozenset({"question", "answer"}),
}


def source_response(source: KnowledgeSource) -> KnowledgeSourceResponse:
    visible = _VISIBLE_DETAILS[source.type]
    details = {key: value for key, value in source.configuration.items() if key in visible}
    return KnowledgeSourceResponse(
        id=source.id,
        bot_id=source.bot_id,
        type=source.type,
        name=source.name,
        status=source.status,
        details=details,
        error_code=source.error_code,
        error_message=source.error_message,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


__all__ = [
    "KnowledgeSourceResponse",
    "ManualSourceCreateRequest",
    "ManualSourceUpdateRequest",
    "WebsiteSourceCreateRequest",
    "source_response",
]
