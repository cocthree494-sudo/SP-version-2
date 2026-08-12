# Universal Support Agent — Technical Plan

> Goal: build a fast, multilingual, low-cost, reliable multi-tenant customer-support SaaS. Companies connect their own knowledge, publish a support bot, and later use the same core across web, WhatsApp, Telegram, Messenger, and email.

Project decisions and session history live in [CONTEXT.md](CONTEXT.md). Execution order lives in [TASKS.md](TASKS.md).

## 1. Product boundary

There are three user types:

1. **End customer** — asks the support bot questions.
2. **Tenant member/admin** — manages a company, bots, knowledge, and analytics.
3. **Platform admin** — operates the SaaS; full admin tooling is deferred.

### Phase 1 outcome

The first usable slice must let a tenant:

1. create an account and organization;
2. create a bot;
3. add knowledge from a file, website, or manual Q&A;
4. wait for ingestion and see its status;
5. test the bot in a playground;
6. optionally connect its own approved model-generation provider credential and choose an explicit routing/fallback policy;
7. embed a fast web widget;
8. view basic usage.

Billing, a live-agent inbox, and non-web channels are intentionally not required for this slice.

## 2. Locked architecture decisions

| Area | Decision | Reason |
|---|---|---|
| Backend | Python 3.12+ and async FastAPI | Strong AI/data ecosystem, typed API, good streaming support |
| Dashboard | Next.js App Router with TypeScript | Dynamic UI, mature ecosystem, SSR where useful, strong production tooling |
| Web widget | Preact + Vite, shipped as an isolated custom element | Much smaller customer-site bundle than shipping the full dashboard runtime |
| Primary data | PostgreSQL + pgvector | Relational SaaS data and vector search in one operational system |
| Cache/queue | Redis | Rate limiting, short-lived session data, provider health, ingestion jobs |
| ORM/migrations | SQLAlchemy 2 async + Alembic | Explicit schema and portable migrations |
| Background jobs | Redis-backed worker; start with ARQ behind an application interface | Keeps parsing/crawling/embedding outside request processes without heavy infrastructure |
| Object storage | Storage interface: local filesystem in development, S3-compatible in production | Hosting remains undecided and storage can change without domain rewrites |
| Streaming | HTTP Server-Sent Events over `fetch` | Simple infrastructure, proxy-friendly, adequate for one-way token streaming |
| API contract | Versioned REST under `/v1`; OpenAPI generates frontend types | Keeps Python and TypeScript contracts synchronized |
| Deployment | Docker-first and environment-configured | Can move between VPS and managed cloud without code changes |
| Provider ownership | Platform-managed model targets are the default; a tenant may optionally bring its own generation-provider credentials (BYOK) through approved adapters or the Phase 2 hardened custom-provider path | Keeps onboarding simple while allowing customer-controlled spend, limits, and provider access; custom endpoints require egress controls to prevent secret exfiltration |
| BYOK secret custody | Provider-neutral envelope-encryption/KMS or Vault adapter; plaintext exists only briefly at submission and provider-call boundaries | Tenant API keys must never become ordinary database, browser, log, prompt, or support-visible data |

Model names and provider credentials must be configuration, not hard-coded business logic. The initial policy can use a low-cost model for normal turns and promote difficult turns to a stronger model. BYOK extends the same provider-neutral interfaces; it must not fork the agent into tenant-specific processes or deployments.

## 3. Repository shape

```text
support-agent/
├─ apps/
│  ├─ api/                    # FastAPI application
│  │  ├─ app/
│  │  │  ├─ api/             # HTTP routes and dependencies
│  │  │  ├─ core/            # settings, security, logging, tenancy
│  │  │  ├─ db/              # models, sessions, migrations helpers
│  │  │  ├─ domains/         # auth, bots, knowledge, chat, usage
│  │  │  ├─ providers/       # LLM, embedding, storage adapters
│  │  │  ├─ workers/         # ingestion/crawl jobs
│  │  │  └─ main.py
│  │  ├─ alembic/
│  │  └─ tests/
│  └─ web/                    # Next.js tenant dashboard
├─ packages/
│  ├─ widget/                 # embeddable Preact chat widget
│  └─ api-client/             # generated TypeScript client/types
├─ infra/
│  ├─ docker/
│  └─ compose.yaml
├─ docs/
├─ .env.example
└─ task runner/config files
```

Domain code must not import a channel implementation. A channel adapter converts external events into one internal chat request and converts the internal response back to the channel format.

## 4. Request and agent flow

```text
Channel adapter
  -> resolve tenant + bot + public/private identity
  -> enforce allowed origin, auth, quota, and rate limit
  -> load conversation summary and recent turns
  -> retrieve tenant-scoped knowledge
  -> resolve tenant provider policy and eligible targets
  -> select model tier/provider
  -> generate grounded answer with citations
  -> validate/fallback
  -> persist messages and usage
  -> stream response to channel
```

### Answering rules

- Always answer in the customer's language unless the tenant explicitly configures another language.
- Treat retrieved documents as untrusted data, not instructions.
- Prefer a clear “I do not know based on the available information” over fabrication.
- Expose source citations in the playground and where a channel supports them.
- Keep provider-specific payloads inside provider adapters.
- Never send secrets, unrelated tenant data, or the entire knowledge base to a model. A provider adapter may place the selected credential only in that provider's authenticated transport header, never in prompt content.

## 5. Multi-tenant data model draft

All tenant-owned tables carry `tenant_id`. Global identity tables are the only justified exception. IDs use UUIDs; timestamps are UTC.

| Table | Important fields / purpose |
|---|---|
| `users` | email, password hash, status; global identity |
| `tenants` | name, slug, status, settings |
| `tenant_memberships` | tenant_id, user_id, role (`owner/admin/member`) |
| `bots` | tenant_id, name, system policy, default language, status |
| `bot_keys` | tenant_id, bot_id, public publishable-key identifier, allowed origins, revoked_at; future secret credentials must be hashed |
| `knowledge_sources` | tenant_id, bot_id, type, name, source URL/file reference, status, error |
| `documents` | tenant_id, source_id, checksum, title, canonical URL, metadata, version |
| `document_chunks` | tenant_id, document_id, ordinal, content, token count, embedding vector, metadata |
| `conversations` | tenant_id, bot_id, channel, external/session identity, summary, status |
| `messages` | tenant_id, conversation_id, role, content, citations, model metadata |
| `usage_events` | append-only tenant_id, historical bot/conversation IDs, operation, provider/model, input/output/cache tokens, latency_ms, estimated_cost_microusd |
| `ingestion_jobs` | tenant_id, source_id, job type, state, attempts, progress, error |
| `provider_credentials` | tenant_id, approved generation-provider type, encrypted secret envelope/reference, safe label, fingerprint/masked suffix, status, verification/rotation/revocation timestamps; raw secrets are never readable through the API |
| `provider_policies` | tenant_id, routing mode (`platform_only`, `tenant_first_with_platform_fallback`, `tenant_only`), ordered tenant target references, and explicit platform-fallback setting |

Likely later tables: `subscriptions`, `invoices`, `tickets`, `agent_assignments`, `audit_logs`, and channel-specific installations. Do not add them to Phase 1 without a task or a direct user request.

### Isolation rules

- Tenant scope is established once at the request boundary and passed explicitly.
- Every tenant query must include tenant scope; repository helpers make unscoped access difficult.
- PostgreSQL row-level security is defense in depth, not a substitute for application checks.
- Cache keys, job payloads, storage paths, logs, and vector queries include `tenant_id`.
- Provider credential and policy lookup is tenant-scoped and fail-closed; decrypted secrets are never cached in shared application caches or placed on queues.
- Cross-tenant isolation tests are release-blocking.

## 6. Knowledge ingestion

### Common pipeline

```text
create source
  -> enqueue idempotent job
  -> fetch/read input
  -> normalize text and metadata
  -> deduplicate by checksum
  -> chunk with overlap and structural boundaries
  -> embed in batches
  -> atomically activate new document version
  -> mark source ready or failed
```

Source types:

- **File:** PDF, DOCX, TXT, and Markdown. Enforce size/type limits and never trust client MIME alone.
- **Website:** crawl a bounded allow-listed domain with robots/rate controls, canonical URLs, depth/page limits, and SSRF protection.
- **Manual Q&A:** store a question/answer pair as an authoritative short document.

Jobs are retryable and idempotent. A failed re-ingestion must not delete the last usable document version.

## 7. Retrieval and memory

Phase 1 retrieval should combine:

1. pgvector semantic similarity;
2. PostgreSQL lexical/full-text relevance;
3. metadata filters for tenant, bot, source status, and language;
4. lightweight score fusion and duplicate removal.

Only the best small set of chunks is sent to the model. Retrieval returns source IDs and offsets so citations can be traced.

Conversation context uses recent turns plus a server-generated rolling summary. Durable “customer memory” beyond conversation continuity is Phase 2 because it introduces consent, correction, and retention requirements.

## 8. Model router, cost, and failover

### Tiering

- Start normal grounded questions on a configured low-cost model.
- Promote when retrieval is weak, the question is multi-step, a policy requires it, the first answer fails validation, or a tool workflow is complex.
- Keep routing rules observable: store why a tier/provider was chosen.
- Cache stable system/tool prefixes where the provider supports prompt caching.

### Provider interface

The orchestrator depends on an internal interface such as `generate`, `stream`, `embed`, health state, and normalized usage. Provider adapters translate errors into retryable, throttled, unavailable, invalid-request, or fatal categories.

### Failover policy

1. Apply a strict per-attempt timeout and total request budget.
2. Retry only transient failures with bounded exponential backoff and jitter.
3. Open a provider/model circuit after repeated failures; store short-lived state in Redis.
4. Route to the next healthy configured provider/model.
5. Never retry non-idempotent external tools blindly.
6. If all providers fail, return a safe localized message and retain the trace for diagnosis.

Provider-level Claude redundancy through direct API, Bedrock, or Vertex is a later reliability milestone. The interface is built in Phase 1 so adding it does not rewrite the agent.

### Tenant BYOK policy

- Platform-managed configured targets remain the default, so a tenant can use the product without supplying a secret.
- A tenant may configure multiple provider targets. The router may fail over among that tenant's healthy targets before considering a platform target.
- Routing modes are explicit: `platform_only`, `tenant_first_with_platform_fallback`, or `tenant_only`. Platform fallback for a BYOK tenant is never silently enabled.
- `tenant_only` must fail safely when its targets are unavailable or revoked; it must not spend platform credentials behind the tenant's back.
- Credential resolution occurs after authenticated tenant scope is established and immediately before adapter execution. Router traces contain credential IDs/status and routing reasons, never raw keys.
- Revocation invalidates in-process credential/target caches immediately; a revoked target cannot wait for a general cache TTL to expire.
- Phase 1 BYOK covers answer-generation providers only and uses approved provider adapters/endpoints. Phase 2 tasks T-071 through T-074 add a Hermes-aligned provider catalog and a hardened custom OpenAI-compatible generation-endpoint path; embedding BYOK still requires vector-model/dimension compatibility and re-indexing rules and remains separate.
- Credentials for later external integrations require separate scopes, storage rules, and tasks.

## 9. API surface draft

Exact payloads are defined task-by-task and documented in OpenAPI.

```text
GET    /health/live
GET    /health/ready

POST   /v1/auth/register
POST   /v1/auth/login
POST   /v1/auth/refresh
GET    /v1/me

GET    /v1/tenants/current
PATCH  /v1/tenants/current

POST   /v1/bots
GET    /v1/bots
GET    /v1/bots/{bot_id}
PATCH  /v1/bots/{bot_id}
DELETE /v1/bots/{bot_id}

POST   /v1/bots/{bot_id}/keys
GET    /v1/bots/{bot_id}/keys
PATCH  /v1/bots/{bot_id}/keys/{key_id}
DELETE /v1/bots/{bot_id}/keys/{key_id}

POST   /v1/bots/{bot_id}/sources/files
POST   /v1/bots/{bot_id}/sources/websites
POST   /v1/bots/{bot_id}/sources/manual
GET    /v1/bots/{bot_id}/sources
GET    /v1/sources/{source_id}
DELETE /v1/sources/{source_id}

POST   /v1/bots/{bot_id}/conversations
POST   /v1/conversations/{conversation_id}/messages   # optional SSE stream
GET    /v1/conversations/{conversation_id}/messages

GET    /v1/usage/summary

POST   /v1/providers/credentials
GET    /v1/providers/credentials
POST   /v1/providers/credentials/{credential_id}/verify
PUT    /v1/providers/credentials/{credential_id}/secret   # rotate; secret is write-only
DELETE /v1/providers/credentials/{credential_id}          # revoke
GET    /v1/providers/policy
PATCH  /v1/providers/policy

GET    /v1/widget/{public_bot_key}/config
```

Public widget requests use a revocable publishable bot key, allowed-origin checks, rate limits, and a short-lived anonymous session token. A publishable key is an identifier, not a secret.

## 10. Security and privacy baseline

- Password hashing with Argon2id; short-lived access tokens and rotated refresh tokens.
- Secrets only through environment/secret managers; never committed or logged.
- Tenant provider secrets use envelope encryption through a replaceable KMS/Vault-style adapter. Store ciphertext plus key/reference metadata, not plaintext or a reversibly obfuscated application field.
- Credential create/rotate accepts a secret once over TLS; every response returns only masked metadata. Raw keys are never re-displayed, written to browser storage, sent to an LLM, included in job payloads, or exposed in logs, traces, analytics, exceptions, support tools, or API validation bodies.
- Decrypt only just in time inside the provider-call boundary; support rotation and immediate revocation, and redact known provider-key formats as defense in depth.
- File size/type validation and sanitized filenames.
- Website crawler blocks loopback, link-local, private networks, unsafe schemes, and redirect escapes.
- HTML/Markdown rendered in the dashboard/widget is sanitized.
- Logs redact authorization headers, tokens, message bodies by default, and personal data where possible.
- Configurable retention/deletion hooks are designed into conversations and source documents.
- Prompt-injection tests ensure knowledge content cannot override system/tenant policy.

## 11. Performance targets

Targets are budgets to measure, not guarantees before load testing:

- Widget loader: small, lazy-loaded, isolated from host CSS, and no dashboard framework payload.
- Dashboard: server-render shells where useful; client JavaScript only for interactive areas.
- API health/auth/list endpoints: p95 under 300 ms in the normal deployment region.
- Chat: first streamed event quickly; provider latency reported separately from application overhead.
- Retrieval: p95 under 500 ms for MVP-scale tenant corpora.
- No ingestion parsing or embedding runs in the web request process.

## 12. Testing and observability

- Backend: unit tests plus PostgreSQL/Redis integration tests.
- Frontend/widget: component tests and a small set of Playwright critical-path tests.
- Contract: generated TypeScript types checked against FastAPI OpenAPI.
- Mandatory isolation tests attempt cross-tenant reads/writes for every tenant-owned domain.
- BYOK tests cover cross-tenant credential/policy isolation, API masking, ciphertext-at-rest behavior, log/error redaction, verify/rotate/revoke, tenant-only failure, tenant-target failover, and opt-in platform fallback.
- Structured JSON logs include request/trace ID, tenant ID, bot ID, latency, route, and normalized error class.
- Metrics include request latency/errors, queue depth, ingestion duration, retrieval scores, provider/model health, token usage, and estimated cost.

## 13. Delivery phases

### Phase 1 — working web MVP

Foundation, tenant/auth, three knowledge sources, ingestion/retrieval, provider-neutral agent, optional secure tenant BYOK for answer generation, memory compaction, playground, web widget, usage tracking, and deployment/runbook.

### Phase 2 — channels and reliability

Multi-provider failover in production, Telegram, WhatsApp, Messenger, email adapters, tenant analytics, and consent-aware long-term customer memory.

### Phase 3 — business and human operations

Stripe plans/quotas/invoices, fuller account management, platform admin tooling, human handoff inbox, assignment, and takeover.

### Phase 4 — growth

Deflection/CSAT/cost analytics, voice, approved auto-learning from resolved tickets, and selected external integrations only if users request them.

## 14. Explicitly open

- Production hosting/vendor and budget.
- Exact platform-managed model and embedding provider IDs/credentials; tenant BYOK support is scheduled separately and remains optional.
- Brand/design direction.
- The additional feature ideas the user intended to share; capture them in [FEATURES.md](FEATURES.md).

These do not block the hosting-agnostic scaffold. Missing provider credentials must be handled with a deterministic mock until credentials are supplied.
