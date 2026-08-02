"""Validated HTTP contracts for minimal dashboard authentication."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator

from app.domains.tenancy.enums import MembershipRole, TenantStatus, UserStatus

_slug_separator = re.compile(r"[^a-z0-9]+")
_valid_slug = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def create_organization_slug(name: str) -> str:
    """Create a stable ASCII slug, with a safe fallback for non-Latin names."""

    ascii_name = (
        unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    )
    slug = _slug_separator.sub("-", ascii_name.casefold()).strip("-")[:63].rstrip("-")
    if len(slug) >= 2:
        return slug
    return f"org-{uuid4().hex[:12]}"


def normalize_organization_slug(value: str) -> str:
    normalized = value.strip().casefold()
    if not 2 <= len(normalized) <= 63 or _valid_slug.fullmatch(normalized) is None:
        raise ValueError(
            "Organization slug must be 2-63 lowercase letters, numbers, or hyphens"
        )
    return normalized


class RegisterRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr
    password: SecretStr = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    organization_name: str = Field(min_length=2, max_length=200)
    organization_slug: str | None = None

    @field_validator("organization_slug")
    @classmethod
    def validate_slug(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_organization_slug(value)


class LoginRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr
    password: SecretStr = Field(min_length=1, max_length=128)
    organization_slug: str | None = None

    @field_validator("organization_slug")
    @classmethod
    def validate_slug(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_organization_slug(value)


class RefreshRequest(BaseModel):
    refresh_token: SecretStr = Field(min_length=32, max_length=256)


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth token type, not a credential
    expires_in: int


class CurrentTenantResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    status: TenantStatus


class MeResponse(BaseModel):
    id: UUID
    email: EmailStr
    display_name: str | None
    status: UserStatus
    created_at: datetime
    tenant: CurrentTenantResponse
    role: MembershipRole


__all__ = [
    "CurrentTenantResponse",
    "LoginRequest",
    "MeResponse",
    "RefreshRequest",
    "RegisterRequest",
    "TokenPairResponse",
    "create_organization_slug",
    "normalize_organization_slug",
]
