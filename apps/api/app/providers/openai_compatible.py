"""Configurable OpenAI-compatible chat and embedding provider adapters."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
from pydantic import SecretStr

from app.providers.embeddings import (
    EmbeddingBatch,
    EmbeddingProviderError,
    EmbeddingUsage,
    estimate_tokens,
)
from app.providers.types import (
    ChatMessage,
    GenerationRequest,
    GenerationResponse,
    MessageRole,
    ProviderError,
    ProviderErrorCategory,
    ProviderUsage,
    StreamEvent,
    StreamEventType,
)

_UNTRUSTED_TOOL_DATA_PREFIX = "UNTRUSTED_TOOL_DATA:\n"


def _category_for_status(status_code: int) -> ProviderErrorCategory:
    if status_code in {401, 403}:
        return ProviderErrorCategory.AUTHENTICATION
    if status_code == 408:
        return ProviderErrorCategory.TIMEOUT
    if status_code == 429:
        return ProviderErrorCategory.THROTTLED
    if status_code >= 500:
        return ProviderErrorCategory.UNAVAILABLE
    if status_code >= 400:
        return ProviderErrorCategory.INVALID_REQUEST
    return ProviderErrorCategory.FATAL


def _public_error_message(category: ProviderErrorCategory) -> str:
    messages = {
        ProviderErrorCategory.TIMEOUT: "AI provider request timed out",
        ProviderErrorCategory.THROTTLED: "AI provider is rate limited",
        ProviderErrorCategory.UNAVAILABLE: "AI provider is temporarily unavailable",
        ProviderErrorCategory.AUTHENTICATION: "AI provider authentication failed",
        ProviderErrorCategory.INVALID_REQUEST: "AI provider rejected the request",
        ProviderErrorCategory.INVALID_RESPONSE: "AI provider returned an invalid response",
        ProviderErrorCategory.FATAL: "AI provider request failed",
    }
    return messages[category]


def _usage(payload: Any) -> ProviderUsage:
    if not isinstance(payload, dict):
        return ProviderUsage()
    prompt_details = payload.get("prompt_tokens_details")
    cached = prompt_details.get("cached_tokens", 0) if isinstance(prompt_details, dict) else 0
    return ProviderUsage(
        input_tokens=int(payload.get("prompt_tokens", 0) or 0),
        output_tokens=int(payload.get("completion_tokens", 0) or 0),
        cache_read_tokens=int(cached or 0),
    )


class _OpenAICompatibleBase:
    def __init__(
        self,
        *,
        provider_id: str,
        model_id: str,
        base_url: str,
        api_key: SecretStr,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.provider_id = provider_id
        self.model_id = model_id
        self._api_key = api_key
        self._request_headers = {
            "Authorization": f"Bearer {api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(
            base_url=f"{base_url.rstrip('/')}/",
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
        )

    def _error(
        self,
        category: ProviderErrorCategory,
        status_code: int | None = None,
    ) -> ProviderError:
        return ProviderError(
            category,
            _public_error_message(category),
            provider_id=self.provider_id,
            status_code=status_code,
        )

    async def _post(self, path: str, payload: dict[str, Any]) -> httpx.Response:
        try:
            response = await self.client.post(path, json=payload, headers=self._request_headers)
        except httpx.TimeoutException as exc:
            raise self._error(ProviderErrorCategory.TIMEOUT) from exc
        except httpx.RequestError as exc:
            raise self._error(ProviderErrorCategory.UNAVAILABLE) from exc
        if response.is_error:
            category = _category_for_status(response.status_code)
            raise self._error(category, response.status_code)
        return response

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()


class OpenAICompatibleLLMProvider(_OpenAICompatibleBase):
    def __init__(
        self,
        *,
        supports_standalone_tool_messages: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.supports_standalone_tool_messages = supports_standalone_tool_messages

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        response = await self._post("chat/completions", self._payload(request, stream=False))
        try:
            payload = response.json()
            choice = payload["choices"][0]
            text = choice["message"]["content"]
            if not isinstance(text, str):
                raise TypeError
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise self._error(ProviderErrorCategory.INVALID_RESPONSE) from exc
        return GenerationResponse(
            text=text,
            finish_reason=choice.get("finish_reason"),
            usage=_usage(payload.get("usage")),
            provider_id=self.provider_id,
            model_id=self.model_id,
        )

    async def stream(self, request: GenerationRequest) -> AsyncIterator[StreamEvent]:
        payload = self._payload(request, stream=True)
        try:
            async with self.client.stream(
                "POST",
                "chat/completions",
                json=payload,
                headers=self._request_headers,
            ) as response:
                if response.is_error:
                    category = _category_for_status(response.status_code)
                    raise self._error(category, response.status_code)
                finish_reason = None
                final_usage = ProviderUsage()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line.removeprefix("data:").strip()
                    if data == "[DONE]":
                        break
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError as exc:
                        raise self._error(ProviderErrorCategory.INVALID_RESPONSE) from exc
                    final_usage = _usage(event.get("usage")) or final_usage
                    choices = event.get("choices") or []
                    if not choices:
                        continue
                    choice = choices[0]
                    delta = choice.get("delta", {}).get("content")
                    if isinstance(delta, str) and delta:
                        yield StreamEvent(type=StreamEventType.TEXT_DELTA, text=delta)
                    if choice.get("finish_reason") is not None:
                        finish_reason = str(choice["finish_reason"])
                yield StreamEvent(
                    type=StreamEventType.COMPLETED,
                    finish_reason=finish_reason,
                    usage=final_usage,
                )
        except httpx.TimeoutException as exc:
            raise self._error(ProviderErrorCategory.TIMEOUT) from exc
        except httpx.RequestError as exc:
            raise self._error(ProviderErrorCategory.UNAVAILABLE) from exc

    def _payload(self, request: GenerationRequest, *, stream: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model_id,
            "messages": [self._message_payload(message) for message in request.messages],
            "max_tokens": request.max_output_tokens,
            "temperature": request.temperature,
            "stream": stream,
        }
        if request.stop:
            payload["stop"] = request.stop
        if stream:
            payload["stream_options"] = {"include_usage": True}
        return payload

    def _message_payload(self, message: ChatMessage) -> dict[str, str]:
        if (
            message.role is MessageRole.TOOL
            and not self.supports_standalone_tool_messages
        ):
            return {
                "role": MessageRole.USER.value,
                "content": f"{_UNTRUSTED_TOOL_DATA_PREFIX}{message.content}",
            }
        return {"role": message.role.value, "content": message.content}


class OpenAICompatibleEmbeddingProvider(_OpenAICompatibleBase):
    def __init__(
        self,
        *,
        dimensions: int,
        request_dimensions: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.dimensions = dimensions
        # Providers that support Matryoshka truncation need the requested width
        # in the request body; without it EMBEDDING_DIMENSIONS is silently
        # ignored and the stored vectors do not match the configured column.
        self.request_dimensions = request_dimensions

    async def embed(self, texts: list[str]) -> EmbeddingBatch:
        if not texts:
            return EmbeddingBatch(embeddings=[], usage=EmbeddingUsage(input_tokens=0))
        payload: dict[str, Any] = {"model": self.model_id, "input": texts}
        if self.request_dimensions:
            payload["dimensions"] = self.dimensions
        try:
            response = await self._post("embeddings", payload)
        except ProviderError as exc:
            raise EmbeddingProviderError(
                exc.category,
                exc.public_message,
                provider_id=exc.provider_id,
                status_code=exc.status_code,
            ) from exc
        try:
            payload_json = response.json()
            data = payload_json["data"]
            if not isinstance(data, list):
                raise TypeError
            # Some OpenAI-compatible providers, including Gemini, omit `index`.
            # The response order matches the input order, so fall back to it
            # rather than failing the whole batch.
            if all(isinstance(item, dict) and "index" in item for item in data):
                data = sorted(data, key=lambda item: int(item["index"]))
            embeddings = [item["embedding"] for item in data]
            if not all(
                isinstance(embedding, list)
                and all(isinstance(value, (float, int)) for value in embedding)
                for embedding in embeddings
            ):
                raise TypeError
        except (KeyError, TypeError, ValueError) as exc:
            raise EmbeddingProviderError(
                ProviderErrorCategory.INVALID_RESPONSE,
                _public_error_message(ProviderErrorCategory.INVALID_RESPONSE),
                provider_id=self.provider_id,
            ) from exc
        if any(len(embedding) != self.dimensions for embedding in embeddings):
            raise EmbeddingProviderError(
                ProviderErrorCategory.INVALID_RESPONSE,
                "AI provider returned embeddings with an unexpected dimension",
                provider_id=self.provider_id,
            )
        usage = payload_json.get("usage")
        if isinstance(usage, dict):
            input_tokens = int(usage.get("prompt_tokens", 0))
        else:
            # Providers that omit usage would otherwise report zero embedding
            # cost forever. Estimate instead so cost tracking stays meaningful.
            input_tokens = sum(estimate_tokens(text) for text in texts)
        return EmbeddingBatch(
            embeddings=[[float(value) for value in embedding] for embedding in embeddings],
            usage=EmbeddingUsage(input_tokens=input_tokens),
        )


__all__ = ["OpenAICompatibleEmbeddingProvider", "OpenAICompatibleLLMProvider"]
