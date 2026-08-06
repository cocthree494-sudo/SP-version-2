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

## Tenant-owned generation keys (T-046)

Organizations may optionally bring an OpenAI generation key. Owner and admin
roles can create, list, verify, rotate, and revoke credentials through
`/v1/providers/credentials`; member roles cannot access this surface. Secret
inputs are write-only. Responses contain only the label, provider, configured
model IDs, lifecycle timestamps, status, and a last-four-character mask.

Each secret is encrypted with a new AES-256-GCM data key. That data key is then
wrapped by the configured `BYOK_MASTER_KEY`, with tenant ID, credential ID, and
provider bound as authenticated data. Production deployments must inject the
URL-safe base64 master key and `BYOK_MASTER_KEY_VERSION` through a secret manager.
The local wrapper is an adapter boundary for moving key wrapping to KMS or Vault.
Database backups contain ciphertext and wrapped data keys, never plaintext keys.

`/v1/providers/policy` makes routing explicit:

- `platform_only` never decrypts or uses a tenant credential.
- `tenant_first_with_platform_fallback` tries verified tenant targets first and
  then the configured platform targets.
- `tenant_only` fails safely when no verified active tenant target is available.

Policy and credential state are loaded for every generation request, so rotation
and revocation take effect on the next request. Revocation removes the credential
from the active policy order. Tenant keys are accepted only for the approved
OpenAI API endpoint; arbitrary base URLs and embedding BYOK remain out of scope.

Operational logs, validation errors, normalized provider failures, API responses,
jobs, prompts, and shared circuit/cache keys must never contain raw credentials.
Compromise of the application plus its wrapping key remains a custody risk, so
production should restrict secret-manager access, audit decrypt operations,
rotate wrapping keys, encrypt backups, and keep database and key-management
permissions separated.

## Dashboard provider settings (T-055)

Owners and admins manage generation BYOK at `/dashboard/providers`. The page can
add an OpenAI key, trigger live verification, rotate or revoke it, and order
verified active credentials for the tenant policy. It explains and exposes only
the three backend routing modes; embedding keys and arbitrary provider URLs are
not offered.

Raw keys use password inputs with browser autocomplete disabled. They exist only
in transient component/form state, are cleared after every add or rotate attempt,
never enter `localStorage`/`sessionStorage`, and are never re-displayed. All list,
status, error, and policy views use masked metadata returned by the API. Members
do not call or see the provider-management API surface.
