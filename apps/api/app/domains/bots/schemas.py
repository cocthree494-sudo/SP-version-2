"""Validated API contracts and browser-origin canonicalization for bots."""

from __future__ import annotations

import ipaddress
import re
from datetime import datetime
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domains.bots.enums import BotStatus

_language_tag = re.compile(r"^[a-z]{2,8}(?:-[a-z0-9]{1,8})*$")


def normalize_language(value: str) -> str:
    normalized = value.strip().casefold()
    if normalized != "auto" and _language_tag.fullmatch(normalized) is None:
        raise ValueError("default_language must be 'auto' or a BCP 47-style language tag")
    return normalized


def normalize_origin(value: str) -> str:
    """Return an exact, browser-compatible HTTP(S) origin without a path."""

    raw = value.strip()
    parts = urlsplit(raw)
    scheme = parts.scheme.casefold()
    if scheme not in {"http", "https"}:
        raise ValueError("Allowed origins must use http or https")
    if parts.username is not None or parts.password is not None:
        raise ValueError("Allowed origins cannot contain credentials")
    if parts.path not in {"", "/"} or parts.query or parts.fragment:
        raise ValueError("Allowed origins cannot contain a path, query, or fragment")
    if parts.hostname is None:
        raise ValueError("Allowed origins must include a host")

    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError("Allowed origin has an invalid port") from exc

    host = parts.hostname.casefold()
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ValueError("Allowed origin has an invalid host") from exc
    else:
        host = f"[{ip.compressed}]" if ip.version == 6 else ip.compressed

    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        port = None
    port_suffix = "" if port is None else f":{port}"
    return f"{scheme}://{host}{port_suffix}"


def normalize_origins(values: list[str]) -> list[str]:
    """Canonicalize and de-duplicate origins while retaining input order."""

    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        origin = normalize_origin(value)
        if origin not in seen:
            normalized.append(origin)
            seen.add(origin)
    return normalized


class BotCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    system_policy: str | None = Field(default=None, max_length=20_000)
    default_language: str = "auto"
    status: BotStatus = BotStatus.ACTIVE

    @field_validator("default_language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        return normalize_language(value)


class BotUpdateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=200)
    system_policy: str | None = Field(default=None, max_length=20_000)
    default_language: str | None = None
    status: BotStatus | None = None

    @field_validator("default_language")
    @classmethod
    def validate_language(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_language(value)

    @model_validator(mode="after")
    def require_update(self) -> BotUpdateRequest:
        if not self.model_fields_set:
            raise ValueError("At least one bot field must be provided")
        for required_field in ("name", "default_language", "status"):
            if required_field in self.model_fields_set and getattr(self, required_field) is None:
                raise ValueError(f"{required_field} cannot be null")
        return self


class BotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    system_policy: str | None
    default_language: str
    status: BotStatus
    created_at: datetime
    updated_at: datetime


class BotKeyCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    label: str = Field(default="Default", min_length=1, max_length=100)
    allowed_origins: list[str] = Field(min_length=1, max_length=20)

    @field_validator("allowed_origins")
    @classmethod
    def validate_origins(cls, value: list[str]) -> list[str]:
        return normalize_origins(value)


class BotKeyUpdateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    label: str | None = Field(default=None, min_length=1, max_length=100)
    allowed_origins: list[str] | None = Field(default=None, min_length=1, max_length=20)

    @field_validator("allowed_origins")
    @classmethod
    def validate_origins(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return normalize_origins(value)

    @model_validator(mode="after")
    def require_update(self) -> BotKeyUpdateRequest:
        if not self.model_fields_set:
            raise ValueError("At least one key field must be provided")
        for field_name in self.model_fields_set:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class BotKeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    bot_id: UUID
    publishable_key: str
    label: str
    allowed_origins: list[str]
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime


__all__ = [
    "BotCreateRequest",
    "BotKeyCreateRequest",
    "BotKeyResponse",
    "BotKeyUpdateRequest",
    "BotResponse",
    "BotUpdateRequest",
    "normalize_language",
    "normalize_origin",
    "normalize_origins",
]
