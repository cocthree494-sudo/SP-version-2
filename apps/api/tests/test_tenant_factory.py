"""Focused tenant-provider verification behavior."""

from __future__ import annotations

from pydantic import SecretStr

from app.domains.provider_access.enums import GenerationProvider
from app.providers import tenant_factory
from app.providers.types import GenerationResponse, ProviderUsage


class _FakeVerifierAdapter:
    request = None

    async def generate(self, request):
        type(self).request = request
        return GenerationResponse(
            text="OK",
            finish_reason="stop",
            usage=ProviderUsage(),
            provider_id="test",
            model_id="test-model",
        )

    async def aclose(self):
        return None


async def _run_verification(monkeypatch):
    def fake_provider(**_kwargs):
        return _FakeVerifierAdapter()

    monkeypatch.setattr(tenant_factory, "_provider", fake_provider)
    await tenant_factory.LiveCredentialVerifier().verify(
        provider=GenerationProvider.GEMINI,
        model_id="gemini-2.5-flash",
        secret=SecretStr("test-secret"),
    )


def test_live_verifier_allows_reasoning_before_text(monkeypatch):
    import asyncio

    asyncio.run(_run_verification(monkeypatch))

    assert _FakeVerifierAdapter.request is not None
    assert _FakeVerifierAdapter.request.max_output_tokens == 128
    assert _FakeVerifierAdapter.request.temperature == 0
