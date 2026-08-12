"""Write-only secret inputs and masked provider-access responses."""

from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from app.domains.provider_access.catalog import ProviderCatalogEntry, provider_catalog
from app.domains.provider_access.enums import (
    GenerationProvider,
    ProviderCredentialStatus,
    ProviderRoutingMode,
)

_MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")


def _model_id(value: str) -> str:
    normalized = value.strip()
    if _MODEL_ID.fullmatch(normalized) is None:
        raise ValueError("model ID contains unsupported characters")
    return normalized


class ProviderCredentialCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    provider: GenerationProvider
    label: str = Field(min_length=1, max_length=100)
    api_key: SecretStr = Field(min_length=16, max_length=2048)
    base_url: str | None = Field(default=None, max_length=2048)
    low_cost_model_id: str
    strong_model_id: str | None = None

    @field_validator("low_cost_model_id", "strong_model_id")
    @classmethod
    def validate_model_id(cls, value: str | None) -> str | None:
        return None if value is None else _model_id(value)

    @model_validator(mode="after")
    def validate_catalog_model(self) -> ProviderCredentialCreateRequest:
        entry = next((item for item in provider_catalog() if item.id == self.provider.value), None)
        if (entry is None or not entry.enabled) and self.provider.value != "custom":
            raise ValueError("This provider is not currently available")
        if self.provider.value == "custom" and not self.base_url:
            raise ValueError("A verified HTTPS base URL is required for a custom provider")
        if self.provider.value != "custom" and self.base_url is not None:
            raise ValueError("A base URL is only accepted for custom providers")
        valid_models = {item.id for item in entry.models}
        if self.low_cost_model_id not in valid_models:
            raise ValueError("Select a supported low-cost model from the provider catalog")
        if self.strong_model_id is not None and self.strong_model_id not in valid_models:
            raise ValueError("Select a supported strong model from the provider catalog")
        return self


class ProviderCredentialRotateRequest(BaseModel):
    api_key: SecretStr = Field(min_length=16, max_length=2048)


class ProviderCredentialResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider: GenerationProvider
    label: str
    masked_secret: str
    low_cost_model_id: str
    strong_model_id: str | None
    status: ProviderCredentialStatus
    verified_at: datetime | None
    rotated_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ProviderPolicyUpdateRequest(BaseModel):
    mode: ProviderRoutingMode
    credential_order: list[UUID] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def validate_policy(self) -> ProviderPolicyUpdateRequest:
        if len(set(self.credential_order)) != len(self.credential_order):
            raise ValueError("credential_order cannot contain duplicates")
        if self.mode is ProviderRoutingMode.PLATFORM_ONLY and self.credential_order:
            raise ValueError("platform_only cannot include tenant credentials")
        if self.mode is not ProviderRoutingMode.PLATFORM_ONLY and not self.credential_order:
            raise ValueError("tenant routing requires at least one credential")
        return self


class ProviderPolicyResponse(BaseModel):
    mode: ProviderRoutingMode
    credential_order: list[UUID]


class ProviderCatalogModelResponse(BaseModel):
    id: str
    label: str
    base_url: str | None


class ProviderCatalogEntryResponse(BaseModel):
    id: str
    label: str
    aliases: list[str]
    setup_method: str
    credential_env: str | None
    model_discovery: str
    enabled: bool
    availability_reason: str | None
    models: list[ProviderCatalogModelResponse]

    @classmethod
    def from_catalog(cls, entry: ProviderCatalogEntry) -> ProviderCatalogEntryResponse:
        return cls(
            id=entry.id,
            label=entry.label,
            aliases=list(entry.aliases),
            setup_method=entry.setup_method,
            credential_env=entry.credential_env,
            model_discovery=entry.model_discovery,
            enabled=entry.enabled,
            availability_reason=entry.availability_reason,
            models=[
                ProviderCatalogModelResponse(id=model.id, label=model.label)
                for model in entry.models
            ],
        )


class CustomProviderModelsRequest(BaseModel):
    base_url: str = Field(min_length=8, max_length=2048)
    api_key: SecretStr = Field(min_length=16, max_length=2048)


__all__ = [
    "CustomProviderModelsRequest",
    "ProviderCatalogEntryResponse",
    "ProviderCatalogModelResponse",
    "ProviderCredentialCreateRequest",
    "ProviderCredentialResponse",
    "ProviderCredentialRotateRequest",
    "ProviderPolicyResponse",
    "ProviderPolicyUpdateRequest",
]
