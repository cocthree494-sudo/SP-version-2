"""SSRF-safe OpenAI-compatible custom endpoint validation and discovery."""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse

import httpx
from pydantic import SecretStr

from app.providers.openai_compatible import OpenAICompatibleLLMProvider
from app.providers.types import ProviderError, ProviderErrorCategory

_MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
_MAX_MODELS_RESPONSE_BYTES = 1_048_576
_BLOCKED_IPS = {ipaddress.ip_address("169.254.169.254"), ipaddress.ip_address("100.100.100.200")}


class CustomEndpointSecurityError(ValueError):
    """Raised when a tenant endpoint is not a safe public HTTPS destination."""


def _public_addresses(hostname: str) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
    try:
        records = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise CustomEndpointSecurityError(
            "The custom endpoint hostname could not be resolved"
        ) from exc
    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for _family, _kind, _proto, _canonname, sockaddr in records:
        try:
            address = ipaddress.ip_address(sockaddr[0])
        except ValueError as exc:
            raise CustomEndpointSecurityError(
                "The custom endpoint returned an invalid address"
            ) from exc
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
            or address in _BLOCKED_IPS
        ):
            raise CustomEndpointSecurityError(
                "Private, local, link-local, or metadata endpoints are not allowed"
            )
        addresses.append(address)
    if not addresses:
        raise CustomEndpointSecurityError("The custom endpoint has no public address")
    return tuple(addresses)


def validate_custom_base_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise CustomEndpointSecurityError(
            "Custom providers require an HTTPS URL without embedded credentials"
        )
    if parsed.fragment or parsed.query:
        raise CustomEndpointSecurityError("Custom endpoint URLs cannot contain a query or fragment")
    if parsed.port not in (None, 443):
        raise CustomEndpointSecurityError("Custom endpoints must use HTTPS port 443")
    _public_addresses(parsed.hostname)
    return normalized


async def discover_custom_models(base_url: str, api_key: SecretStr) -> list[str]:
    safe_url = validate_custom_base_url(base_url)
    headers = {
        "Authorization": f"Bearer {api_key.get_secret_value()}",
        "Accept": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            # Re-check DNS immediately before every egress request to reduce
            # DNS-rebinding risk; redirects are intentionally disabled.
            validate_custom_base_url(safe_url)
            response = await client.get(f"{safe_url}/models", headers=headers)
            if response.is_redirect or response.is_error:
                raise CustomEndpointSecurityError("The custom endpoint rejected model discovery")
            if (
                int(response.headers.get("content-length", len(response.content)))
                > _MAX_MODELS_RESPONSE_BYTES
            ):
                raise CustomEndpointSecurityError("The custom endpoint response is too large")
            payload = response.json()
    except CustomEndpointSecurityError:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise CustomEndpointSecurityError(
            "The custom endpoint model catalog could not be read"
        ) from exc
    items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise CustomEndpointSecurityError("The custom endpoint returned an invalid model catalog")
    models = [
        str(item["id"])
        for item in items
        if isinstance(item, dict)
        and isinstance(item.get("id"), str)
        and _MODEL_ID.fullmatch(item["id"])
    ]
    if not models:
        raise CustomEndpointSecurityError("The custom endpoint returned no usable models")
    return models[:100]


def custom_provider(
    base_url: str, model_id: str, api_key: SecretStr
) -> OpenAICompatibleLLMProvider:
    try:
        safe_url = validate_custom_base_url(base_url)
    except CustomEndpointSecurityError as exc:
        raise ProviderError(
            ProviderErrorCategory.INVALID_REQUEST, str(exc), provider_id="custom"
        ) from exc
    return OpenAICompatibleLLMProvider(
        provider_id="custom",
        model_id=model_id,
        base_url=safe_url,
        api_key=api_key,
        timeout_seconds=30.0,
    )


__all__ = [
    "CustomEndpointSecurityError",
    "custom_provider",
    "discover_custom_models",
    "validate_custom_base_url",
]
