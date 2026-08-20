"""Adapter registry and catalog readiness contract tests."""

from app.domains.provider_access.catalog import provider_catalog
from app.domains.provider_access.enums import GenerationProvider
from app.providers.adapters import adapter_for, adapter_specs


def test_every_enabled_catalog_provider_has_one_explicit_adapter() -> None:
    specs = {item.provider.value: item for item in adapter_specs()}
    enabled = {item.id for item in provider_catalog() if item.enabled}
    assert enabled == set(specs)
    assert all(
        item.provider.value == "custom" or item.base_url.startswith("https://")
        for item in specs.values()
    )
    assert all(item.kind == "openai_compatible" for item in specs.values())


def test_unverified_native_provider_is_not_accidentally_routable() -> None:
    entry = next(item for item in provider_catalog() if item.id == "anthropic")
    assert entry.enabled is False
    try:
        adapter_for(GenerationProvider.ANTHROPIC)
    except ValueError as exc:
        assert "verified adapter" in str(exc)
    else:
        raise AssertionError("unverified provider unexpectedly became routable")


def test_gemini_uses_the_approved_google_openai_compatible_endpoint() -> None:
    entry = next(item for item in provider_catalog() if item.id == "gemini")
    spec = adapter_for(GenerationProvider.GEMINI)

    assert entry.enabled is True
    assert entry.setup_method == "api_key"
    assert {model.id for model in entry.models} >= {
        "gemini-2.5-flash",
        "gemini-2.5-pro",
    }
    assert spec.base_url == "https://generativelanguage.googleapis.com/v1beta/openai"
    assert spec.kind == "openai_compatible"
    assert spec.supports_standalone_tool_messages is False
