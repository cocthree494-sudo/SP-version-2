# Provider-neutral AI adapters

T-040 separates model-provider payloads from the agent domain.

`LLMProvider` exposes normalized `generate` and `stream` operations using
provider-neutral chat messages, generation settings, finish reasons, stream
events, and usage. `EmbeddingProvider` returns ordered vectors and normalized
input-token usage. Model and provider IDs come only from settings.

Development and tests default to deterministic chat and embedding providers, so
the repository needs no paid key. `AI_PROVIDER_MODE=openai_compatible` selects a
configurable HTTP adapter using `AI_BASE_URL`, `AI_API_KEY`, `LLM_MODEL_ID`,
`EMBEDDING_MODEL_ID`, dimensions, and a strict request timeout. The adapter
supports non-streaming chat, SSE chat streaming, and batch embeddings.

Provider failures are normalized as timeout, throttled, unavailable,
authentication, invalid request, invalid response, or fatal. Only timeout,
throttling, and unavailability are retryable. Error strings and representations
never include response bodies, request messages, or credentials. Production
configuration requires HTTPS for the compatible endpoint.

T-041 composes these interfaces in a low-cost-first `ModelRouter`. Retrieval,
complexity, policy, and validation signals can promote a request to the strong
tier. Every completed route exposes its initial and selected reason plus the
provider/model attempts. Transient errors receive bounded exponential retries,
then healthy configured targets are tried in order.

Circuit state can be process-local for tests or shared in Redis for deployed
API workers. Circuits are keyed by provider and model ID, never by credentials.
Streaming can retry or fail over only before any text is emitted, preventing a
second provider from silently splicing a different answer into a partial stream.
If no target completes within the total request budget, callers receive a safe
terminal error without provider response bodies or secrets.
