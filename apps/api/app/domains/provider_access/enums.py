"""Stable provider-access lifecycle and routing values."""

from enum import StrEnum


class GenerationProvider(StrEnum):
    AI_GATEWAY = "ai-gateway"
    ALIBABA = "alibaba"
    ALIBABA_CODING_PLAN = "alibaba-coding-plan"
    ANTHROPIC = "anthropic"
    ARCEE = "arcee"
    ACTUAL = "actual"
    AZURE_FOUNDRY = "azure-foundry"
    BEDROCK = "bedrock"
    COPILOT = "copilot"
    COPILOT_ACP = "copilot-acp"
    CUSTOM = "custom"
    DEEPSEEK = "deepseek"
    FIREWORKS = "fireworks"
    GMI = "gmi"
    GEMINI = "gemini"
    HUGGINGFACE = "huggingface"
    KILOCODE = "kilocode"
    KIMI = "kimi"
    KIMI_CN = "kimi-cn"
    LMSTUDIO = "lmstudio"
    MINIMAX = "minimax"
    MINIMAX_CN = "minimax-cn"
    MINIMAX_OAUTH = "minimax-oauth"
    NOVITA = "novita"
    NVIDIA = "nvidia"
    NOUS_PORTAL = "nous-portal"
    OPENAI = "openai"
    OPENAI_CODEX = "openai-codex"
    OPENROUTER = "openrouter"
    OPENCODE_GO = "opencode-go"
    OPENCODE_ZEN = "opencode-zen"
    OLLAMA_CLOUD = "ollama-cloud"
    QWEN_OAUTH = "qwen-oauth"
    STEP_FUN = "stepfun"
    TENCENT_TOKENHUB = "tencent-tokenhub"
    XAI = "xai"
    XAI_OAUTH = "xai-oauth"
    XIAOMI = "xiaomi"
    VERTEX = "vertex"
    ZAI = "zai"


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
