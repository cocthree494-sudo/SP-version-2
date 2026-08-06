"""Resolve encrypted tenant BYOK policy into approved generation targets."""

from __future__ import annotations

from uuid import UUID

from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.envelope import EnvelopeCipher, configured_envelope_cipher
from app.domains.provider_access.enums import (
    GenerationProvider,
    ProviderCredentialStatus,
    ProviderRoutingMode,
)
from app.domains.provider_access.repositories import (
    ProviderCredentialRepository,
    ProviderPolicyRepository,
)
from app.domains.provider_access.service import ProviderAccessService
from app.providers.factory import build_llm_targets
from app.providers.openai_compatible import OpenAICompatibleLLMProvider
from app.providers.router import ModelTarget, ModelTier
from app.providers.types import ChatMessage, GenerationRequest, MessageRole

_APPROVED_BASE_URLS = {
    GenerationProvider.OPENAI: "https://api.openai.com/v1",
}


class TenantProviderUnavailableError(RuntimeError):
    """Safe failure when an explicit tenant-only policy has no usable target."""


def _provider(
    *,
    provider: GenerationProvider,
    provider_id: str,
    model_id: str,
    secret: SecretStr,
) -> OpenAICompatibleLLMProvider:
    return OpenAICompatibleLLMProvider(
        provider_id=provider_id,
        model_id=model_id,
        base_url=_APPROVED_BASE_URLS[provider],
        api_key=secret,
        timeout_seconds=settings.AI_REQUEST_TIMEOUT_SECONDS,
    )


class LiveCredentialVerifier:
    async def verify(
        self,
        *,
        provider: GenerationProvider,
        model_id: str,
        secret: SecretStr,
    ) -> None:
        adapter = _provider(
            provider=provider,
            provider_id=f"tenant-verification:{provider.value}",
            model_id=model_id,
            secret=secret,
        )
        try:
            await adapter.generate(
                GenerationRequest(
                    messages=[
                        ChatMessage(
                            role=MessageRole.USER,
                            content="Reply with OK to verify this provider credential.",
                        )
                    ],
                    max_output_tokens=2,
                    temperature=0,
                )
            )
        finally:
            await adapter.aclose()


async def build_tenant_llm_targets(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    cipher: EnvelopeCipher | None = None,
) -> list[ModelTarget]:
    """Load policy on every request so rotation/revocation is immediately effective."""

    policy = await ProviderPolicyRepository(session, tenant_id).get()
    if policy is None or policy.mode is ProviderRoutingMode.PLATFORM_ONLY:
        return build_llm_targets()

    credential_ids = [UUID(item) for item in policy.credential_order]
    credentials = await ProviderCredentialRepository(session, tenant_id).get_ordered(
        credential_ids
    )
    active = [
        credential
        for credential in credentials
        if credential.status is ProviderCredentialStatus.VERIFIED
        and credential.revoked_at is None
    ]
    tenant_targets: list[ModelTarget] = []
    if active:
        access = ProviderAccessService(
            session,
            tenant_id,
            cipher=cipher or configured_envelope_cipher(),
        )
        for credential in active:
            secret = access.decrypt(credential)
            provider_id = (
                f"tenant:{tenant_id}:{credential.provider.value}:{credential.id}"
            )
            tenant_targets.append(
                ModelTarget(
                    provider=_provider(
                        provider=credential.provider,
                        provider_id=provider_id,
                        model_id=credential.low_cost_model_id,
                        secret=secret,
                    ),
                    tier=ModelTier.LOW_COST,
                )
            )
            if credential.strong_model_id is not None:
                tenant_targets.append(
                    ModelTarget(
                        provider=_provider(
                            provider=credential.provider,
                            provider_id=provider_id,
                            model_id=credential.strong_model_id,
                            secret=secret,
                        ),
                        tier=ModelTier.STRONG,
                    )
                )

    if policy.mode is ProviderRoutingMode.TENANT_ONLY:
        if not tenant_targets:
            raise TenantProviderUnavailableError(
                "Tenant-only provider routing has no verified active target"
            )
        return tenant_targets
    return [*tenant_targets, *build_llm_targets()]


__all__ = [
    "LiveCredentialVerifier",
    "TenantProviderUnavailableError",
    "build_tenant_llm_targets",
]
