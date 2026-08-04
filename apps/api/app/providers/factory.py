"""Configuration-only provider selection for domain consumers."""

from __future__ import annotations

from typing import cast

from pydantic import SecretStr

from app.core.config import settings
from app.providers.embeddings import DeterministicEmbeddingProvider, EmbeddingProvider
from app.providers.llm import DeterministicLLMProvider, LLMProvider
from app.providers.openai_compatible import (
    OpenAICompatibleEmbeddingProvider,
    OpenAICompatibleLLMProvider,
)
from app.providers.router import ModelTarget, ModelTier


def _configured_credentials() -> tuple[str, SecretStr]:
    if settings.AI_BASE_URL is None or settings.AI_API_KEY is None:
        raise RuntimeError("Configured AI provider credentials are unavailable")
    return settings.AI_BASE_URL, settings.AI_API_KEY


def _build_llm_provider(model_id: str) -> LLMProvider:
    if settings.AI_PROVIDER_MODE == "deterministic":
        return DeterministicLLMProvider(model_id=model_id)
    base_url, api_key = _configured_credentials()
    return cast(
        LLMProvider,
        OpenAICompatibleLLMProvider(
            provider_id=settings.AI_PROVIDER_ID,
            model_id=model_id,
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=settings.AI_REQUEST_TIMEOUT_SECONDS,
        ),
    )


def build_llm_provider() -> LLMProvider:
    return _build_llm_provider(settings.LLM_MODEL_ID)


def build_llm_targets() -> list[ModelTarget]:
    targets = [
        ModelTarget(
            provider=_build_llm_provider(settings.LLM_MODEL_ID),
            tier=ModelTier.LOW_COST,
            input_cost_microusd_per_million=(
                settings.LLM_INPUT_COST_MICROUSD_PER_MILLION
            ),
            output_cost_microusd_per_million=(
                settings.LLM_OUTPUT_COST_MICROUSD_PER_MILLION
            ),
        )
    ]
    if settings.LLM_STRONG_MODEL_ID:
        targets.append(
            ModelTarget(
                provider=_build_llm_provider(settings.LLM_STRONG_MODEL_ID),
                tier=ModelTier.STRONG,
                input_cost_microusd_per_million=(
                    settings.LLM_STRONG_INPUT_COST_MICROUSD_PER_MILLION
                ),
                output_cost_microusd_per_million=(
                    settings.LLM_STRONG_OUTPUT_COST_MICROUSD_PER_MILLION
                ),
            )
        )
    return targets


def build_embedding_provider() -> EmbeddingProvider:
    if settings.AI_PROVIDER_MODE == "deterministic":
        return DeterministicEmbeddingProvider()
    base_url, api_key = _configured_credentials()
    return cast(
        EmbeddingProvider,
        OpenAICompatibleEmbeddingProvider(
            provider_id=settings.EMBEDDING_PROVIDER_ID,
            model_id=settings.EMBEDDING_MODEL_ID,
            dimensions=settings.EMBEDDING_DIMENSIONS,
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=settings.AI_REQUEST_TIMEOUT_SECONDS,
        ),
    )


__all__ = ["build_embedding_provider", "build_llm_provider", "build_llm_targets"]
