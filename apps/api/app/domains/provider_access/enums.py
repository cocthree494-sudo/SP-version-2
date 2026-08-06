"""Stable provider-access lifecycle and routing values."""

from enum import StrEnum


class GenerationProvider(StrEnum):
    OPENAI = "openai"


class ProviderCredentialStatus(StrEnum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    INVALID = "invalid"
    REVOKED = "revoked"


class ProviderRoutingMode(StrEnum):
    PLATFORM_ONLY = "platform_only"
    TENANT_FIRST_WITH_PLATFORM_FALLBACK = "tenant_first_with_platform_fallback"
    TENANT_ONLY = "tenant_only"


__all__ = [
    "GenerationProvider",
    "ProviderCredentialStatus",
    "ProviderRoutingMode",
]
