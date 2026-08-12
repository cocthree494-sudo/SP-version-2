"""Provider adapter registry.

Every provider exposed as usable in the catalog must have an explicit adapter
specification.  Protocol-compatible providers share the hardened OpenAI
transport; native/cloud/oauth entries stay unavailable until their dedicated
adapter is registered and verified.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.domains.provider_access.catalog import provider_catalog
from app.domains.provider_access.enums import GenerationProvider

AdapterKind = Literal["openai_compatible"]


@dataclass(frozen=True, slots=True)
class ProviderAdapterSpec:
    provider: GenerationProvider
    kind: AdapterKind
    base_url: str
    model_discovery: Literal["live", "maintained"]


_BASE_URLS: dict[GenerationProvider, str] = {
    GenerationProvider.CUSTOM: "",
    GenerationProvider.AI_GATEWAY: "https://ai-gateway.vercel.sh/v1",
    GenerationProvider.ALIBABA: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    GenerationProvider.ALIBABA_CODING_PLAN: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    GenerationProvider.ARCEE: "https://api.arcee.ai/api/v1",
    GenerationProvider.DEEPSEEK: "https://api.deepseek.com/v1",
    GenerationProvider.FIREWORKS: "https://api.fireworks.ai/inference/v1",
    GenerationProvider.GMI: "https://api.gmi-serving.com/v1",
    GenerationProvider.HUGGINGFACE: "https://router.huggingface.co/v1",
    GenerationProvider.KIMI: "https://api.moonshot.ai/v1",
    GenerationProvider.KIMI_CN: "https://api.moonshot.cn/v1",
    GenerationProvider.MINIMAX: "https://api.minimax.io/v1",
    GenerationProvider.MINIMAX_CN: "https://api.minimaxi.com/v1",
    GenerationProvider.NOVITA: "https://api.novita.ai/openai/v1",
    GenerationProvider.NVIDIA: "https://integrate.api.nvidia.com/v1",
    GenerationProvider.OPENAI: "https://api.openai.com/v1",
    GenerationProvider.OPENROUTER: "https://openrouter.ai/api/v1",
    GenerationProvider.OLLAMA_CLOUD: "https://ollama.com/v1",
    GenerationProvider.STEP_FUN: "https://api.stepfun.com/v1",
    GenerationProvider.XAI: "https://api.x.ai/v1",
    GenerationProvider.ZAI: "https://open.bigmodel.cn/api/paas/v4",
}


def adapter_specs() -> tuple[ProviderAdapterSpec, ...]:
    """Return only adapters that are safe to expose to tenants."""

    discovery = {entry.id: entry.model_discovery for entry in provider_catalog()}
    return tuple(
        ProviderAdapterSpec(
            provider=provider,
            kind="openai_compatible",
            base_url=base_url,
            model_discovery=("live" if discovery.get(provider.value) == "live" else "maintained"),
        )
        for provider, base_url in _BASE_URLS.items()
    )


def adapter_for(provider: GenerationProvider) -> ProviderAdapterSpec:
    try:
        return next(item for item in adapter_specs() if item.provider is provider)
    except StopIteration as exc:
        raise ValueError(f"No verified adapter is available for {provider.value}") from exc


__all__ = ["ProviderAdapterSpec", "adapter_for", "adapter_specs"]
