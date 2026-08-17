"""Data-driven provider catalog used by the credential setup experience.

The catalog is intentionally separate from :class:`GenerationProvider`. T-071
surfaces the complete Hermes-aligned provider map in the UI while T-072 enables
only providers with an explicit, tested adapter specification. Future native
adapter work can enable entries without changing the setup screen.
"""

# The catalog rows are intentionally kept compact and readable as a source map.

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SetupMethod = Literal["api_key", "oauth", "cloud_account", "local_endpoint", "custom_endpoint"]
ModelDiscovery = Literal["live", "maintained", "oauth", "local"]

_OPENAI_COMPATIBLE_READY = {
    "openrouter",
    "fireworks",
    "novita",
    "ai-gateway",
    "zai",
    "kimi",
    "kimi-cn",
    "arcee",
    "gmi",
    "minimax",
    "minimax-cn",
    "xai",
    "alibaba",
    "alibaba-coding-plan",
    "deepseek",
    "huggingface",
    "gemini",
    "nvidia",
    "ollama-cloud",
    "stepfun",
}

# Keep this revision next to the source URL so a catalog change is auditable.
HERMES_PROVIDER_SOURCE_URL = "https://hermes-agent.nousresearch.com/docs/integrations/providers"
HERMES_PROVIDER_SOURCE_REVISION = "6aaa181f0eb4dd517d9cf163733e7e41a8e126e1"


@dataclass(frozen=True, slots=True)
class ProviderCatalogModel:
    id: str
    label: str


@dataclass(frozen=True, slots=True)
class ProviderCatalogEntry:
    id: str
    label: str
    aliases: tuple[str, ...]
    setup_method: SetupMethod
    credential_env: str | None
    model_discovery: ModelDiscovery
    enabled: bool
    availability_reason: str | None
    models: tuple[ProviderCatalogModel, ...]


def _models(*items: tuple[str, str]) -> tuple[ProviderCatalogModel, ...]:
    return tuple(ProviderCatalogModel(id=item[0], label=item[1]) for item in items)


def _coming_soon(
    provider_id: str,
    label: str,
    aliases: tuple[str, ...],
    setup_method: SetupMethod,
    model_discovery: ModelDiscovery,
    models: tuple[ProviderCatalogModel, ...],
) -> ProviderCatalogEntry:
    ready = provider_id in _OPENAI_COMPATIBLE_READY
    return ProviderCatalogEntry(
        id=provider_id,
        label=label,
        aliases=aliases,
        setup_method=setup_method,
        credential_env="TENANT_API_KEY" if ready else None,
        model_discovery=model_discovery,
        enabled=ready,
        availability_reason=(
            None if ready else "Adapter planned in T-072; setup will unlock after verification."
        ),
        models=models,
    )


PROVIDER_CATALOG: tuple[ProviderCatalogEntry, ...] = (
    ProviderCatalogEntry(
        id="openai",
        label="OpenAI API",
        aliases=("openai", "gpt"),
        setup_method="api_key",
        credential_env="OPENAI_API_KEY",
        model_discovery="live",
        enabled=True,
        availability_reason=None,
        models=_models(
            ("gpt-4.1-mini", "GPT-4.1 mini"),
            ("gpt-4.1", "GPT-4.1"),
            ("gpt-4o-mini", "GPT-4o mini"),
            ("gpt-4o", "GPT-4o"),
        ),
    ),
    _coming_soon(
        "nous-portal",
        "Nous Portal",
        ("nous", "portal"),
        "oauth",
        "oauth",
        _models(("hermes-3-llama-3.1-405b", "Hermes 3 405B")),
    ),
    _coming_soon(
        "openai-codex",
        "OpenAI Codex",
        ("codex",),
        "oauth",
        "oauth",
        _models(("gpt-5-codex", "GPT-5 Codex")),
    ),
    _coming_soon(
        "copilot",
        "GitHub Copilot",
        ("github", "copilot"),
        "oauth",
        "oauth",
        _models(("github-copilot", "GitHub Copilot")),
    ),
    _coming_soon(
        "copilot-acp",
        "GitHub Copilot ACP",
        ("copilot acp",),
        "oauth",
        "oauth",
        _models(("github-copilot-acp", "GitHub Copilot ACP")),
    ),
    _coming_soon(
        "anthropic",
        "Anthropic",
        ("claude",),
        "api_key",
        "maintained",
        _models(
            ("claude-sonnet-4-0", "Claude Sonnet"),
            ("claude-3-7-sonnet-latest", "Claude 3.7 Sonnet"),
        ),
    ),
    _coming_soon(
        "openrouter",
        "OpenRouter",
        ("router",),
        "api_key",
        "live",
        _models(
            ("openrouter/auto", "Auto routing"), ("anthropic/claude-sonnet-4", "Claude Sonnet")
        ),
    ),
    _coming_soon(
        "fireworks",
        "Fireworks AI",
        ("fireworks ai",),
        "api_key",
        "live",
        _models(("accounts/fireworks/models/llama-v3p1-70b-instruct", "Llama 3.1 70B")),
    ),
    _coming_soon(
        "novita",
        "NovitaAI",
        ("novita ai",),
        "api_key",
        "live",
        _models(("deepseek/deepseek-v3-0324", "DeepSeek V3")),
    ),
    _coming_soon(
        "ai-gateway",
        "Vercel AI Gateway",
        ("gateway",),
        "api_key",
        "live",
        _models(("gateway/auto", "Gateway auto")),
    ),
    _coming_soon(
        "zai",
        "z.ai / GLM",
        ("glm", "zhipu"),
        "api_key",
        "maintained",
        _models(("glm-4.5", "GLM-4.5")),
    ),
    _coming_soon(
        "kimi",
        "Kimi / Moonshot",
        ("moonshot",),
        "api_key",
        "maintained",
        _models(("kimi-k2-0711-preview", "Kimi K2")),
    ),
    _coming_soon(
        "kimi-cn",
        "Kimi / Moonshot China",
        ("moonshot china",),
        "api_key",
        "maintained",
        _models(("kimi-k2-0711-preview", "Kimi K2")),
    ),
    _coming_soon(
        "arcee",
        "Arcee AI",
        ("arcee",),
        "api_key",
        "maintained",
        _models(("virtuoso-large", "Virtuoso Large")),
    ),
    _coming_soon(
        "gmi",
        "GMI Cloud",
        ("gmi cloud",),
        "api_key",
        "maintained",
        _models(("deepseek-v3", "DeepSeek V3")),
    ),
    _coming_soon(
        "actual",
        "Actual Computer",
        ("computer",),
        "cloud_account",
        "maintained",
        _models(("actual-computer", "Actual Computer")),
    ),
    _coming_soon(
        "minimax",
        "MiniMax",
        ("minimax",),
        "api_key",
        "maintained",
        _models(("MiniMax-M1", "MiniMax M1")),
    ),
    _coming_soon(
        "minimax-cn",
        "MiniMax China",
        ("minimax china",),
        "api_key",
        "maintained",
        _models(("MiniMax-M1", "MiniMax M1")),
    ),
    _coming_soon(
        "xai",
        "xAI Responses API",
        ("grok", "xai"),
        "api_key",
        "live",
        _models(("grok-4", "Grok 4"), ("grok-3-mini", "Grok 3 mini")),
    ),
    _coming_soon(
        "xai-oauth",
        "xAI Grok OAuth",
        ("grok oauth",),
        "oauth",
        "oauth",
        _models(("grok-4", "Grok 4")),
    ),
    _coming_soon(
        "alibaba",
        "Qwen / Alibaba DashScope",
        ("qwen", "dashscope"),
        "api_key",
        "maintained",
        _models(("qwen-max", "Qwen Max")),
    ),
    _coming_soon(
        "alibaba-coding-plan",
        "Alibaba Coding Plan",
        ("coding plan",),
        "api_key",
        "maintained",
        _models(("qwen3-coder-plus", "Qwen3 Coder Plus")),
    ),
    _coming_soon(
        "kilocode",
        "Kilo Code",
        ("kilo",),
        "api_key",
        "maintained",
        _models(("kilo-auto", "Kilo auto")),
    ),
    _coming_soon(
        "xiaomi",
        "Xiaomi MiMo",
        ("mimo",),
        "api_key",
        "maintained",
        _models(("mimo-v2-flash", "MiMo V2 Flash")),
    ),
    _coming_soon(
        "tencent-tokenhub",
        "Tencent TokenHub",
        ("tokenhub",),
        "api_key",
        "maintained",
        _models(("hunyuan-turbo", "Hunyuan Turbo")),
    ),
    _coming_soon(
        "opencode-zen",
        "OpenCode Zen",
        ("zen",),
        "api_key",
        "maintained",
        _models(("opencode/auto", "OpenCode auto")),
    ),
    _coming_soon(
        "opencode-go",
        "OpenCode Go",
        ("go",),
        "api_key",
        "maintained",
        _models(("opencode-go/auto", "OpenCode Go auto")),
    ),
    _coming_soon(
        "deepseek",
        "DeepSeek",
        ("deepseek",),
        "api_key",
        "live",
        _models(("deepseek-chat", "DeepSeek Chat"), ("deepseek-reasoner", "DeepSeek Reasoner")),
    ),
    _coming_soon(
        "huggingface",
        "Hugging Face",
        ("hf",),
        "api_key",
        "live",
        _models(("Qwen/Qwen3-235B-A22B", "Qwen3 235B")),
    ),
    _coming_soon(
        "gemini",
        "Google / Gemini",
        ("google", "gemini"),
        "api_key",
        "live",
        _models(("gemini-2.5-flash", "Gemini 2.5 Flash"), ("gemini-2.5-pro", "Gemini 2.5 Pro")),
    ),
    _coming_soon(
        "vertex",
        "Google Vertex AI",
        ("vertex",),
        "cloud_account",
        "live",
        _models(("gemini-2.5-flash", "Gemini 2.5 Flash")),
    ),
    _coming_soon(
        "azure-foundry",
        "Azure AI Foundry",
        ("azure", "foundry"),
        "cloud_account",
        "live",
        _models(("deployment-name", "Your deployment")),
    ),
    _coming_soon(
        "bedrock",
        "AWS Bedrock",
        ("aws", "bedrock"),
        "cloud_account",
        "live",
        _models(("anthropic.claude-sonnet-4-0", "Claude Sonnet")),
    ),
    _coming_soon(
        "nvidia",
        "NVIDIA Build",
        ("nvidia",),
        "api_key",
        "live",
        _models(("meta/llama-3.1-70b-instruct", "Llama 3.1 70B")),
    ),
    _coming_soon(
        "ollama-cloud",
        "Ollama Cloud",
        ("ollama",),
        "api_key",
        "live",
        _models(("qwen3:32b", "Qwen3 32B")),
    ),
    _coming_soon(
        "qwen-oauth",
        "Qwen OAuth",
        ("qwen oauth",),
        "oauth",
        "oauth",
        _models(("qwen3-coder-plus", "Qwen3 Coder Plus")),
    ),
    _coming_soon(
        "minimax-oauth",
        "MiniMax OAuth",
        ("minimax oauth",),
        "oauth",
        "oauth",
        _models(("MiniMax-M2", "MiniMax M2")),
    ),
    _coming_soon(
        "stepfun",
        "StepFun",
        ("step",),
        "api_key",
        "maintained",
        _models(("step-3.5-flash", "Step 3.5 Flash")),
    ),
    _coming_soon(
        "lmstudio",
        "LM Studio",
        ("local",),
        "local_endpoint",
        "local",
        _models(("local-model", "Local model")),
    ),
    ProviderCatalogEntry(
        id="custom",
        label="Custom Endpoint",
        aliases=("custom", "openai compatible", "endpoint"),
        setup_method="custom_endpoint",
        credential_env=None,
        model_discovery="local",
        enabled=True,
        availability_reason="Requires a verified public HTTPS endpoint and model discovery.",
        models=_models(("custom-model", "Discovered after verification")),
    ),
)


def provider_catalog() -> tuple[ProviderCatalogEntry, ...]:
    """Return an immutable catalog snapshot for API serialization."""

    return PROVIDER_CATALOG


__all__ = [
    "HERMES_PROVIDER_SOURCE_REVISION",
    "HERMES_PROVIDER_SOURCE_URL",
    "ProviderCatalogEntry",
    "ProviderCatalogModel",
    "provider_catalog",
]
