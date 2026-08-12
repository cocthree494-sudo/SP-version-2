"""Release matrix invariants for the provider-management surface."""

from pathlib import Path

from app.domains.provider_access.catalog import provider_catalog
from app.providers.adapters import adapter_specs


def test_release_matrix_documents_every_enabled_adapter() -> None:
    docs = Path(__file__).resolve().parents[3] / "docs" / "provider-release-readiness.md"
    content = docs.read_text(encoding="utf-8")
    enabled = {entry.id for entry in provider_catalog() if entry.enabled}
    registered = {spec.provider.value for spec in adapter_specs()}
    assert enabled == registered
    assert "Credential custody" in content
    assert "Tenant isolation" in content
    assert "Egress" in content
