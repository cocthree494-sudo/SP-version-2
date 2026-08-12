"""Custom endpoint egress and model-catalog safety tests."""

import pytest

from app.providers.custom_endpoint import CustomEndpointSecurityError, validate_custom_base_url


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/v1",
        "https://127.0.0.1/v1",
        "https://169.254.169.254/latest/meta-data",
        "https://example.com/v1?token=secret",
        "https://user:pass@example.com/v1",
    ],
)
def test_custom_endpoint_rejects_unsafe_destinations(url: str) -> None:
    with pytest.raises(CustomEndpointSecurityError):
        validate_custom_base_url(url)


def test_custom_endpoint_rejects_private_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.providers.custom_endpoint as module

    monkeypatch.setattr(
        module,
        "_public_addresses",
        lambda _host: (_ for _ in ()).throw(CustomEndpointSecurityError("private")),
    )
    with pytest.raises(CustomEndpointSecurityError):
        validate_custom_base_url("https://example.com/v1")
