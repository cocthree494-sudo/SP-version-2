"""Provider-neutral generation, streaming, error, timeout, and secret-safety tests."""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import settings
from app.providers.embeddings import (
    DeterministicEmbeddingProvider,
    EmbeddingProviderError,
)
from app.providers.factory import build_embedding_provider, build_llm_provider
from app.providers.llm import DeterministicLLMProvider
from app.providers.openai_compatible import (
    OpenAICompatibleEmbeddingProvider,
    OpenAICompatibleLLMProvider,
)
from app.providers.types import (
    ChatMessage,
    GenerationRequest,
    MessageRole,
    ProviderError,
    ProviderErrorCategory,
    StreamEventType,
)


def request_fixture() -> GenerationRequest:
    return GenerationRequest(
        messages=[ChatMessage(role=MessageRole.USER, content="How do refunds work?")],
        max_output_tokens=100,
    )


def grounded_request_fixture() -> GenerationRequest:
    return GenerationRequest(
        messages=[
            ChatMessage(role=MessageRole.SYSTEM, content="Use the supplied evidence."),
            ChatMessage(role=MessageRole.TOOL, content='{"KNOWLEDGE_DATA": []}'),
            ChatMessage(role=MessageRole.USER, content="What is supported?"),
        ],
        max_output_tokens=100,
    )


@pytest.mark.asyncio
async def test_deterministic_provider_generate_and_stream_are_stable() -> None:
    provider = DeterministicLLMProvider(
        provider_id="test",
        model_id="configured-model",
        response_text="Refunds take five days.",
        stream_chunk_chars=7,
    )
    response = await provider.generate(request_fixture())
    events = [event async for event in provider.stream(request_fixture())]

    assert response.text == "Refunds take five days."
    assert response.model_id == "configured-model"
    assert response.usage.input_tokens > 0
    assert "".join(event.text for event in events) == response.text
    assert events[-1].type is StreamEventType.COMPLETED
    assert events[-1].usage == response.usage


@pytest.mark.asyncio
async def test_openai_compatible_generation_and_embeddings_use_normalized_types() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-secret-value"
        payload = json.loads(request.content)
        assert payload["model"] in {"chat-config", "embed-config"}
        if request.url.path.endswith("/chat/completions"):
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {"content": "Configured response"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 3,
                        "prompt_tokens_details": {"cached_tokens": 4},
                    },
                },
            )
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0]},
                    {"index": 0, "embedding": [1.0, 0.0]},
                ],
                "usage": {"prompt_tokens": 7},
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://provider.example/v1/",
    ) as client:
        llm = OpenAICompatibleLLMProvider(
            provider_id="configured",
            model_id="chat-config",
            base_url="https://unused.example/v1",
            api_key=SecretStr("test-secret-value"),
            timeout_seconds=5,
            client=client,
        )
        embeddings = OpenAICompatibleEmbeddingProvider(
            provider_id="configured",
            model_id="embed-config",
            dimensions=2,
            base_url="https://unused.example/v1",
            api_key=SecretStr("test-secret-value"),
            timeout_seconds=5,
            client=client,
        )
        generated = await llm.generate(request_fixture())
        embedded = await embeddings.embed(["first", "second"])

    assert generated.text == "Configured response"
    assert generated.usage.cache_read_tokens == 4
    assert embedded.embeddings == [[1.0, 0.0], [0.0, 1.0]]
    assert embedded.usage.input_tokens == 7


@pytest.mark.asyncio
async def test_openai_compatible_stream_normalizes_sse_events() -> None:
    stream_body = "\n".join(
        [
            'data: {"choices":[{"delta":{"content":"Hello "},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"content":"world"},"finish_reason":"stop"}]}',
            'data: {"choices":[],"usage":{"prompt_tokens":2,"completion_tokens":2}}',
            "data: [DONE]",
            "",
        ]
    )

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=stream_body, headers={"content-type": "text/event-stream"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://provider.example/v1/",
    ) as client:
        provider = OpenAICompatibleLLMProvider(
            provider_id="configured",
            model_id="chat-config",
            base_url="https://unused.example/v1",
            api_key=SecretStr("test-secret-value"),
            timeout_seconds=5,
            client=client,
        )
        events = [event async for event in provider.stream(request_fixture())]

    assert "".join(event.text for event in events) == "Hello world"
    assert events[-1].type is StreamEventType.COMPLETED
    assert events[-1].usage is not None
    assert events[-1].usage.input_tokens == 2


@pytest.mark.asyncio
async def test_openai_compatible_retains_standalone_tool_messages() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["messages"][1] == {
            "role": "tool",
            "content": '{"KNOWLEDGE_DATA": []}',
        }
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Supported [1]."}}]},
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://provider.example/v1/",
    ) as client:
        provider = OpenAICompatibleLLMProvider(
            provider_id="configured",
            model_id="chat-config",
            base_url="https://unused.example/v1",
            api_key=SecretStr("test-secret-value"),
            timeout_seconds=5,
            client=client,
        )
        await provider.generate(grounded_request_fixture())


@pytest.mark.asyncio
async def test_compatible_provider_maps_tool_messages_for_generate_and_stream() -> None:
    seen_payloads: list[dict] = []
    stream_body = "\n".join(
        [
            'data: {"choices":[{"delta":{"content":"Supported [1]."},"finish_reason":"stop"}]}',
            "data: [DONE]",
            "",
        ]
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        seen_payloads.append(payload)
        mapped = payload["messages"][1]
        assert mapped["role"] == "user"
        assert mapped["content"].startswith("UNTRUSTED_TOOL_DATA:\n")
        if payload["stream"]:
            return httpx.Response(
                200,
                text=stream_body,
                headers={"content-type": "text/event-stream"},
            )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Supported [1]."}}]},
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://provider.example/v1/",
    ) as client:
        provider = OpenAICompatibleLLMProvider(
            provider_id="gemini-compatible",
            model_id="gemini-2.5-flash",
            base_url="https://unused.example/v1",
            api_key=SecretStr("test-secret-value"),
            timeout_seconds=5,
            client=client,
            supports_standalone_tool_messages=False,
        )
        await provider.generate(grounded_request_fixture())
        events = [event async for event in provider.stream(grounded_request_fixture())]

    assert len(seen_payloads) == 2
    assert seen_payloads[0]["stream"] is False
    assert seen_payloads[1]["stream"] is True
    assert "".join(event.text for event in events) == "Supported [1]."


@pytest.mark.asyncio
async def test_provider_errors_are_retry_classified_and_secret_safe() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream leaked body test-secret-value")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://provider.example/v1/",
    ) as client:
        provider = OpenAICompatibleLLMProvider(
            provider_id="configured",
            model_id="chat-config",
            base_url="https://unused.example/v1",
            api_key=SecretStr("test-secret-value"),
            timeout_seconds=5,
            client=client,
        )
        with pytest.raises(ProviderError) as captured:
            await provider.generate(request_fixture())

    error = captured.value
    assert error.category is ProviderErrorCategory.UNAVAILABLE
    assert error.retryable is True
    assert "test-secret-value" not in str(error)
    assert "test-secret-value" not in repr(error)


@pytest.mark.asyncio
async def test_embedding_request_sends_configured_dimensions() -> None:
    """EMBEDDING_DIMENSIONS must reach the provider, not only the local mock."""

    seen: list[int] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        seen.append(payload["dimensions"])
        return httpx.Response(
            200,
            json={
                "data": [{"index": 0, "embedding": [0.0, 1.0, 0.0, 0.0]}],
                "usage": {"prompt_tokens": 3},
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://provider.example/v1/",
    ) as client:
        provider = OpenAICompatibleEmbeddingProvider(
            provider_id="configured",
            model_id="embed-config",
            dimensions=4,
            base_url="https://unused.example/v1",
            api_key=SecretStr("test-secret-value"),
            timeout_seconds=5,
            client=client,
        )
        embedded = await provider.embed(["first"])

    assert seen == [4]
    assert embedded.embeddings == [[0.0, 1.0, 0.0, 0.0]]


@pytest.mark.asyncio
async def test_embedding_rejects_unexpected_dimensions() -> None:
    """A silently truncated or widened vector must fail instead of being stored."""

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [{"index": 0, "embedding": [0.0, 1.0]}],
                "usage": {"prompt_tokens": 3},
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://provider.example/v1/",
    ) as client:
        provider = OpenAICompatibleEmbeddingProvider(
            provider_id="configured",
            model_id="embed-config",
            dimensions=1536,
            base_url="https://unused.example/v1",
            api_key=SecretStr("test-secret-value"),
            timeout_seconds=5,
            client=client,
        )
        with pytest.raises(EmbeddingProviderError) as captured:
            await provider.embed(["first"])

    assert captured.value.category is ProviderErrorCategory.INVALID_RESPONSE
    assert "test-secret-value" not in str(captured.value)


def test_embedding_configuration_is_independent_of_generation_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real retrieval embeddings must not require replacing the platform LLM."""

    monkeypatch.setattr(settings, "AI_PROVIDER_MODE", "deterministic")
    monkeypatch.setattr(settings, "AI_BASE_URL", None)
    monkeypatch.setattr(settings, "AI_API_KEY", None)
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER_MODE", "openai_compatible")
    monkeypatch.setattr(settings, "EMBEDDING_BASE_URL", "https://embed.example/v1")
    monkeypatch.setattr(settings, "EMBEDDING_API_KEY", SecretStr("embed-secret-value"))
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER_ID", "gemini")
    monkeypatch.setattr(settings, "EMBEDDING_MODEL_ID", "gemini-embedding-001")
    monkeypatch.setattr(settings, "EMBEDDING_DIMENSIONS", 1536)

    embedding_provider = build_embedding_provider()
    llm_provider = build_llm_provider()

    assert isinstance(embedding_provider, OpenAICompatibleEmbeddingProvider)
    assert embedding_provider.dimensions == 1536
    assert embedding_provider.model_id == "gemini-embedding-001"
    assert isinstance(llm_provider, DeterministicLLMProvider)


def test_embedding_configuration_falls_back_to_generation_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Existing single-provider deployments keep working with no new variables."""

    monkeypatch.setattr(settings, "AI_PROVIDER_MODE", "openai_compatible")
    monkeypatch.setattr(settings, "AI_BASE_URL", "https://shared.example/v1")
    monkeypatch.setattr(settings, "AI_API_KEY", SecretStr("shared-secret-value"))
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER_MODE", None)
    monkeypatch.setattr(settings, "EMBEDDING_BASE_URL", None)
    monkeypatch.setattr(settings, "EMBEDDING_API_KEY", None)

    assert settings.embedding_provider_mode == "openai_compatible"
    assert settings.embedding_base_url == "https://shared.example/v1"
    assert isinstance(build_embedding_provider(), OpenAICompatibleEmbeddingProvider)


def test_deterministic_embeddings_stay_available_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "AI_PROVIDER_MODE", "openai_compatible")
    monkeypatch.setattr(settings, "AI_BASE_URL", "https://shared.example/v1")
    monkeypatch.setattr(settings, "AI_API_KEY", SecretStr("shared-secret-value"))
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER_MODE", "deterministic")

    assert isinstance(build_embedding_provider(), DeterministicEmbeddingProvider)
