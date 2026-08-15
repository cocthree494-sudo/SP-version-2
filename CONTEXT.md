# Session Context — Universal Support Agent

> Read this first. This is the compact handoff document for Claude, Codex, or another coding agent. Detailed architecture is in [PLAN.md](PLAN.md); executable order is in [TASKS.md](TASKS.md).

**Last updated:** 2026-08-15, Codex session
**Status:** Phase 1 through T-062 is complete. Final run `31212237732` passed live tests/evaluation, all browser paths, production Compose, restore/recovery, and deterministic performance acceptance.

## 1. Project

Build a multi-tenant SaaS customer-support AI agent. A company signs up, adds its own knowledge base, gets a bot, and uses the same channel-agnostic core on its website and later WhatsApp, Telegram, Messenger, and email.

User priorities:

- world-class answer quality;
- very low model/token cost;
- multilingual replies;
- provider/model failover so one API outage does not take down the bot;
- memory, database, and RAG;
- a visually dynamic, **super-fast** web experience;
- documentation that lets Claude/Codex continue without repeating discovery.

## 2. Decisions

| ID | Decision | Why / source |
|---|---|---|
| D1 | Multi-tenant from day one | Final product is SaaS; tenant isolation cannot be bolted on safely later |
| D2 | Channel-agnostic core; web widget first | All major channels are desired, but each channel should be a thin adapter |
| D3 | Python + FastAPI backend | User chose the recommended backend direction |
| D4 | Human handoff is deferred | User wants the basic working product first |
| D5 | Knowledge sources: website crawl, PDF/DOCX/TXT/MD upload, manual Q&A | User wanted all proposed sources except burdensome external integrations |
| D6 | MVP business layer: auth, organization, roles, usage/token tracking; no Stripe | Recommended minimal SaaS foundation accepted |
| D7 | Work in small, working MVP slices | User accepted the fast-MVP direction and will switch between Claude/Codex when limits are reached |
| D8 | Frontend default: Next.js dashboard + lightweight Preact/Vite widget | Best current fit for dynamic dashboard plus a small customer-site bundle; can change before scaffold if user requests |
| D9 | Docker/env-configured, hosting-agnostic code | Hosting and budget are not decided |
| D10 | Provider/model IDs stay configurable | Enables tiering/failover and avoids vendor logic in the domain layer |
| D11 | Platform-managed generation providers remain the default; tenants may optionally bring their own keys | User accepted optional BYOK with explicit tenant routing/fallback. Keys require encrypted, tenant-isolated, write-only custody; Phase 1 excludes arbitrary base URLs and embedding BYOK |
| D12 | Every registration and explicit login requires a fresh email OTP before session issuance | User requires OTP for password and social authentication; development delivery uses Gmail SMTP behind a replaceable mail-provider boundary |
| D13 | Platform administration is a separate global permission and audited control plane | User promoted a dynamic admin dashboard; tenant owner/admin roles must never imply platform access |

## 3. Deferred scope

Do not build these now unless the user explicitly changes priority:

- Stripe subscription, plan tiers, quota enforcement, invoices;
- full account-management and platform-admin UIs;
- human handoff/live-agent inbox, assignment, takeover;
- Notion, Zendesk, Shopify, Intercom, or similar integrations;
- voice support;
- automatic KB learning from resolved tickets;
- consent-aware long-term customer profile memory.

The Phase 1 schema and interfaces should leave clean extension points for them without implementing them prematurely.

## 4. Technical direction

- FastAPI, Next.js, Preact/Vite widget.
- PostgreSQL + pgvector, Redis, SQLAlchemy/Alembic.
- Redis-backed background ingestion worker.
- Local storage adapter for development and S3-compatible adapter later.
- Hybrid vector + lexical retrieval, citations, grounded fallback.
- Low-cost model first, stronger model promotion for complex/failed cases.
- Provider adapter + normalized errors + retry/circuit-breaker interface.
- Conversation recent-window plus server-side rolling summary.
- Streaming chat over SSE.
- All tenant-owned data, jobs, caches, storage paths, and retrieval are tenant-scoped.

## 5. User instructions that must persist

1. Record important questions, answers, decisions, and completed steps so another AI can continue cheaply.
2. Avoid spending time/tokens building the large SaaS/business layer before the working bot MVP.
3. Keep tasks small enough for one focused coding session.
4. Use task IDs in commit messages, for example: `[T-021] add tenant schema`.
5. The user intended to share more features but could not remember them. Keep [FEATURES.md](FEATURES.md) as the inbox.
6. Tenant BYOK is optional, never a prerequisite for onboarding. Never store, return, log, or send a plaintext customer provider key to the model.

## 6. Session log

### Session 1

- User described the universal support bot, cost, quality, multilingual, failover, memory, DB, and RAG goals.
- Claude proposed the initial architecture and created `CONTEXT.md` and `PLAN.md`.

### Session 2 — Claude

- Asked scope, channel, stack, handoff, hosting, KB sources, SaaS-layer scope, and pace questions.
- Recorded D1–D7 and open hosting/provider questions.
- Recommended a working MVP first and Next.js if the user had no frontend preference.
- Proposed the cross-agent system: `AGENTS.md`, `CLAUDE.md`, `TASKS.md`, a handoff block, and task-ID commits.
- Work stopped because Claude usage reached its limit before those files and Git setup were completed.

### Session 3 — Codex

- Read the pasted Claude terminal conversation and existing docs.
- Inspected `git.png`; identified GitHub repository `cocthree494-sudo/support-agent`.
- Expanded the technical plan and created the task/handoff system.
- Created the extra-feature inbox requested by the user.
- Selected D8 as a reversible implementation default.
- Initialized `main`, connected the HTTPS GitHub remote, committed `[T-001]`, and pushed successfully.

### Session 3b — Codex

- Scaffolded the full monorepo structure: `apps/api`, `apps/web`, `packages/widget`, `packages/api-client`, `infra/`, `scripts/`, and `docs/`.
- Created Docker Compose for PostgreSQL/pgvector and Redis with health checks.
- Set up `npm run dev` one-command startup with `setup.mjs` and `dev.mjs`.
- Configured npm workspaces, `.env.example`, `.editorconfig`, `.gitignore`, `tsconfig.base.json`.
- Created FastAPI scaffold (`app/main.py`), Next.js App Router scaffold, Preact/Vite widget scaffold, and shared `@support-agent/api-client` package.
- Did not commit the work before session ended.

### Session 4 — Antigravity

- Verified the existing uncommitted scaffold satisfied T-010 requirements.
- Added planned API subdirectory structure: `app/api/`, `app/core/`, `app/db/`, `app/domains/`, `app/providers/`, `app/workers/` as Python packages.
- Added `alembic/` placeholder and `tests/__init__.py`.
- Added `docs/README.md` placeholder.
- Verified all Python packages import correctly and both TypeScript projects compile clean.
- Committed all scaffold work as `[T-010]`.
- Implemented T-011: Configured backend tools (Ruff, mypy, pytest) with a smoke test.
- Configured frontend tools (ESLint, Prettier equivalents) for Next.js web app and Preact widget.
- Added a unified `npm run check` script to package.json and a GitHub Actions workflow (`ci.yml`).
- Implemented T-012: Added typed configuration using `pydantic-settings`.
- Added structured JSON logging using `structlog` and correlation IDs.
- Added `/health/live` and `/health/ready` endpoints with basic PostgreSQL and Redis connectivity checks.
- Added unit tests for health endpoints.

### Session 5 — Codex

- Implemented T-020 with an async SQLAlchemy engine, session factory, FastAPI session dependency, and application-shutdown disposal.
- Added shared UUID primary-key, UTC timestamp, constraint-naming, and tenant-scoped model mixins.
- Initialized async Alembic and added revision `0001_enable_pgvector`, which enables the PostgreSQL `vector` extension.
- Reused the shared engine in database readiness checks and added root migration commands.
- Added migration, model-convention, and session-factory tests. Full backend/frontend/widget checks pass.

### Session 6 — Codex

- Implemented T-021 with global `users` and `tenants` tables plus tenant-scoped `tenant_memberships`, stable status/role enums, and normalized email/slug repositories.
- Added explicit `tenant_scope`/`tenant_session_scope` context helpers, transaction-local PostgreSQL `app.tenant_id` configuration, and a forced RLS policy for memberships.
- Added fail-closed membership repository predicates, active-context conflict detection, migration coverage, and SQLite cross-tenant isolation tests.
- Added `docs/tenancy.md` describing the application-predicate plus PostgreSQL-RLS defense-in-depth strategy.
- Verified the full repository quality gate with `npm.cmd run check`.

### Session 7 — Codex

- Implemented T-022 JSON endpoints for register, login, refresh, and the tenant-bound current-user response at `/v1/me`.
- Registration now atomically bootstraps a user, organization, owner membership, and first login session; optional slugs are validated and omitted slugs are generated.
- Added Argon2id password hashing and rehash support, tenant-bound short-lived JWT access tokens, and high-entropy opaque refresh tokens stored only as hashes.
- Added fixed-lifetime refresh-token families with row-locked rotation and whole-family revocation when a rotated token is replayed.
- Tenant-scoped `refresh_tokens` use fail-closed repository predicates and forced RLS. Login has a narrow SELECT-only RLS policy that resolves only the password-verified user's memberships before tenant selection.
- Added migration `0003_auth`, auth/API/isolation tests, and `docs/authentication.md`. The full repository quality gate passes with 20 API tests.

### Session 8 — Codex

- Pushed the seven pending T-010 through T-022 commits to GitHub after the user explicitly authorized the external action.
- Diagnosed the resulting GitHub Actions failure: CI had no local `.env`, so pytest collection lacked required database and Redis URLs. Added explicit test-only workflow environment values in commit `4cf6077`, pushed it, and verified the replacement Actions run completed successfully.
- Implemented T-023 bot create/list/get/update/delete APIs with normalized default language, active/disabled status, owner/admin mutation permissions, and member read access.
- Added public widget-key create/list/update/revoke APIs, exact HTTP(S) origin canonicalization, safe multi-key rotation, and idempotent irreversible revocation.
- Added a reusable public credential resolver that checks tenant-addressed key format, forced tenant scope, bot status, key revocation, and exact allowed origin.
- Added migration `0004_bots` with forced RLS on `bots` and `bot_keys` plus a composite tenant/bot foreign key, API/security/isolation tests, and `docs/bots.md`.
- Verified the full repository quality gate with 25 API tests and inspected all nine bot/key OpenAPI operations.

### Session 9 — Codex

- Pushed T-023 after the user authorized completing and pushing the batch through T-030; its GitHub Actions run completed successfully.
- Implemented T-024 immutable, tenant-scoped usage events with normalized generation/embedding operation, configured provider/model IDs, token/cache counts, integer latency milliseconds, and integer estimated micro-USD.
- Added a transaction-composable internal recorder that validates bot ownership and flushes without forcing a commit, leaving future message plus usage persistence atomic.
- Added `GET /v1/usage/summary` with optional bot and timezone-aware half-open UTC range filters, exact totals, and provider/model/operation breakdowns. No quotas or billing enforcement were added.
- Enforced append-only behavior through repository shape, ORM mutation hooks, and a PostgreSQL update/delete trigger in migration `0005_usage`; added forced RLS and cross-tenant tests.
- Added `docs/usage.md`; the full repository quality gate passes with 30 API tests.

### Session 10 — Codex

- Verified T-024 independently from its commit, migration/API/docs, and focused tests before continuing the user-requested batch through T-040.
- Implemented T-030 local tenant-prefixed atomic object storage, an S3-compatible protocol, durable knowledge/document/job schema, forced RLS, idempotent ARQ dispatch, recovery dispatch, bounded retry state, and the standalone ingestion worker.
- Implemented T-031/T-032 secure streaming PDF/DOCX/TXT/Markdown upload, size/MIME/signature validation, failed-write/source cleanup, deterministic parsers and metadata/title extraction, DOCX archive safety limits, normalized UTF-8 output, source status APIs, and safe parser errors.
- Implemented T-033 staged document versions, structural token-bounded chunking with overlap, deterministic and provider-neutral embeddings, batched chunk persistence, retry classification, and activation only after all chunks succeed.
- Implemented T-034 exact-host bounded website crawling with URL canonicalization, robots/rate controls, page/depth/response/redirect limits, DNS/IP SSRF checks on requests and redirects, useful-text extraction, content/URL deduplication, progress, and per-page versioned embeddings.
- Implemented T-035 authoritative manual Q&A create/edit APIs; content changes enqueue a new embedded version while unchanged edits do not duplicate work.
- Implemented T-036 tenant/bot/source/language-scoped hybrid retrieval using pgvector cosine candidates, PostgreSQL `tsvector`/GIN lexical candidates, reciprocal-rank fusion, exact deduplication, and traceable citation metadata, plus a portable SQLite evaluation path.
- Implemented T-040 normalized LLM/embedding request, stream, usage, and error types; configurable deterministic and OpenAI-compatible adapters; strict timeouts; configuration-only model/provider IDs; and secret-safe errors.
- Added migrations `0006_knowledge_ingestion` and `0007_document_chunks`, knowledge/provider documentation, source/parser/crawler/retrieval/provider/security tests, and inspected the source OpenAPI operations plus PostgreSQL offline SQL.
- Full `npm.cmd run check` passes: Ruff, strict mypy across 79 files, 49 API tests, Next.js lint/typecheck, and widget lint/typecheck.

### Session 11 — Codex

- Implemented T-041 low-cost-first model tiering with configurable strong-model promotion for weak retrieval, complex queries, policy requirements, and validation retries.
- Added bounded exponential retry, per-provider/model circuit state with in-memory and Redis stores, provider/model failover, total request budgets, and safe terminal errors.
- Added observable routing reasons and attempt history for generation plus failover-safe streaming that never switches providers after text has been emitted.
- Added configuration-only model costs/IDs, provider target construction, routing/failure simulation tests, and expanded provider documentation.
- Focused router tests, Ruff, and mypy pass. The full repository gate remains deferred until the user-requested batch through T-050 is complete.
- Implemented T-042 tenant-scoped conversations and ordered messages with forced RLS, composite tenant foreign keys, row-locked sequence allocation, configurable retention, and migration `0008_conversations`.
- Added bounded recent-window loading, incremental rolling-summary interfaces/state, tenant-scoped retention purge hooks, cross-tenant tests, and conversation documentation.
- Four focused conversation/migration tests, targeted Ruff/mypy, and PostgreSQL offline migration rendering pass.
- Implemented T-043 grounded RAG orchestration: tenant/bot-scoped retrieval, bounded prompt assembly, same-language response policy, strong-tier citation-validation retry, localized uncertainty fallback, and traceable citations.
- Kept retrieved chunks and rolling summaries in untrusted tool-data roles with explicit prompt-injection boundaries; tenant policy remains separate trusted system context.
- User/assistant messages and all incurred generation usage (including invalid drafts) now commit atomically with routing metadata and calculated configured cost. Three focused orchestration/security/isolation tests plus targeted Ruff/mypy pass.
- Implemented T-044 short-lived anonymous widget JWTs bound to tenant, bot, key, conversation, exact origin, token ID, and a distinct audience/type; key revocation and bot state are re-checked on every message.
- Added exact-origin dynamic CORS/preflight, Redis Lua fixed-window limits with tenant/bot-scoped hashed identities, fail-closed deployed dependencies, SSE ready/delta/replace/citation/completion/error events, and disconnect stream cleanup.
- Seven focused widget/orchestration tests cover the public flow, origin rejection, revocation, rate limiting, and cancellation without partial persistence; targeted Ruff/mypy pass and OpenAPI exposes both widget routes.
- Implemented T-045 credential-free deterministic evaluation cases and a non-zero-on-failure CLI report covering grounding, fallback, Bengali response behavior, citation enforcement, prompt injection, and cross-tenant conversation rejection.
- `npm.cmd run eval:agent` and its JSON form report PASS (6/6); two focused evaluation tests plus targeted Ruff/mypy pass.

### Session 12 — Codex

- Implemented T-050 with a responsive Next.js landing/auth/dashboard experience, accessible design tokens, loading/error states, and authenticated organization context.
- Added a same-origin authentication BFF: access and rotated refresh tokens stay in `HttpOnly`, `SameSite=Lax` cookies and are never stored in browser storage. The session route validates `/v1/me`, refreshes expired sessions, and clears invalid cookies.
- Protected dashboard rendering waits for session resolution and redirects anonymous users to login. Successful auth honors only safe same-origin `next` paths.
- Added shared typed auth client contracts, `API_INTERNAL_URL`, dashboard/auth documentation, a code-native app icon, and ESLint ignores for generated Next.js output.
- Inspected landing, login, registration, protected redirect, authenticated dashboard, and the mobile navigation drawer with Playwright on desktop and 390-pixel mobile layouts. The authenticated visual state used a browser-only session mock because Docker/PostgreSQL/Redis were unavailable locally.
- Full `npm.cmd run check` passes: Ruff, strict mypy over 97 files, 64 API tests, web lint/typecheck, and widget lint/typecheck.

### Session 13 — Claude (review only, no implementation)

- Performed a full repository review at the user's request; wrote no product code.
- Found that `git log` still ends at `[T-024]` while `TASKS.md` marks `T-030` through `T-050`
  complete. Roughly twenty tasks of implementation, eleven test modules, three migrations, nine
  documentation files, and the entire dashboard exist only as untracked or modified files.
- Found that every test module builds its engine with `sqlite+aiosqlite:///:memory:`, while
  `app/core/tenancy.py` returns early for any non-PostgreSQL dialect. The row-level security
  policies in migrations `0002`–`0008`, the `usage_events` append-only trigger, the pgvector
  branch at `retrieval.py:172`, and every migration upgrade/downgrade path have therefore never
  executed. `app/evals/agent_quality.py:277` grades the SQLite path as well.
- Found that `.github/workflows/ci.yml` sets `DATABASE_URL` and `REDIS_URL` but declares no
  service containers, so nothing listens on those ports and the readiness test passes only
  because it accepts `503`.
- Noted that the `pgvector/pgvector` image creates `POSTGRES_USER` as a superuser, and
  PostgreSQL superusers bypass row-level security even under `FORCE ROW LEVEL SECURITY`. RLS
  tests written without a dedicated non-superuser role would pass while proving nothing.
- Recorded four smaller findings for later tasks: the per-process JWT fallback secret breaks
  multi-worker `uvicorn`; `app/api/health.py` creates a Redis client at import time and
  `main.py` reaches into that global; `redis` was narrowed from `>=8.1.0` to `>=5.2,<6.0` to
  satisfy ARQ without an explanatory note; and `packages/api-client` is still a stub rather than
  OpenAPI-generated types.
- Wrote `CODEX-BRIEF.md`, added release-blocking task `T-013`, and moved the next task from
  `T-051` back to `T-013`. No implementation files were modified.

### Session 14 — Codex

- Protected the previously uncommitted T-030 through T-051 implementation in local commit `e07b120`; T-051 remains unchecked because its completion contract has not been fully verified.
- Added the T-013 verification brief and local artifact ignores in `2b738e1`, then implemented the PostgreSQL/pgvector isolation gate in `35360f1`. None of these commits were pushed.
- Local checks pass with 65 tests passed and 14 PostgreSQL integration tests skipped because this workstation has no Docker, PostgreSQL, or pgvector. Ruff, strict mypy, web/widget lint and typecheck pass; offline upgrade/downgrade SQL renders through migration `0009`; `CI=true` correctly turns a missing PostgreSQL service into a hard failure.
- Kept T-013 unchecked and all later feature work blocked until the integration suite runs against a live non-superuser PostgreSQL role and passes.
- Recorded the user's decision to support optional tenant-owned generation-provider keys. Scheduled the secure backend/routing work as T-046, settings UI as T-055, and lifecycle E2E coverage in T-060. Platform-managed providers stay the default; BYOK is scheduled only and is not implemented.

### Session 15 — Codex

- Pushed the protected implementation, T-013 gate, and BYOK schedule after the user explicitly authorized pushing.
- Ran T-013 through GitHub Actions with live PostgreSQL 16 + pgvector and Redis. The gate exposed and fixed three verification defects: Alembic command arguments were joined incorrectly, PostgreSQL `json` defaults needed a text-normalized comparator because `json` has no equality operator, and test-only mixin models polluted global Alembic metadata.
- Final CI run `30935817080` passed at commit `cbca180`: Ruff passed, strict mypy passed over 102 source files, all 80 tests passed, migrations upgraded/downgraded/upgraded through `0009`, schema/model parity was empty, and the PostgreSQL agent evaluation passed 6/6.
- Live restricted-role tests proved fail-closed and cross-tenant RLS behavior for every current tenant table, raw append-only enforcement for `usage_events`, and tenant-isolated pgvector retrieval. T-013 is complete.

### Session 16 — Codex

- Implemented T-046 tenant-owned OpenAI generation credentials with AES-256-GCM envelope encryption, per-credential data keys, versioned master-key wrapping, tenant-bound authenticated data, masked-only responses, and write-only secret inputs.
- Added owner/admin create, list, verify, rotate, revoke, and routing-policy APIs. Members are denied, repository predicates and forced PostgreSQL RLS protect both new tenant tables, and approved tenant adapters can only target the fixed OpenAI API endpoint.
- Added explicit `platform_only`, `tenant_first_with_platform_fallback`, and fail-closed `tenant_only` routing. Policy and credential state reload on every widget generation request so rotation and revocation apply immediately; embedding BYOK remains excluded.
- Added request-validation redaction for credentials and other secret fields, secret-safe verification errors, migration `0010_provider_access`, live RLS matrix coverage, focused lifecycle/role/tenant/routing tests, environment guidance, and provider custody/threat-boundary documentation.
- Per the user's batch instruction, deferred the broad repository and live PostgreSQL suites. Targeted Ruff and five provider/migration tests pass; the live RLS additions and full suite remain part of the later joint verification phase.
- Completed the T-051 audit of the already-protected dashboard implementation: bot CRUD, role-aware controls, drag/drop multi-file upload, website/manual forms, source status/error display, transitional polling, and destructive confirmations are present and wired to the tenant-authenticated BFF. Web lint and TypeScript checks pass; the prior responsive browser inspection remains documented in `docs/dashboard-management.md`.
- Implemented T-052 with authenticated playground session creation, tenant/channel conversation validation, grounded SSE chat, explicit retrieval/fallback state, visible citations, stream cancellation, conversation reset, and tenant BYOK-aware routing. Added a responsive dashboard playground and bot-filtered token/request/latency/cost/model usage summary.
- T-052 targeted Ruff, web ESLint, and TypeScript checks pass. API behavioral and browser E2E coverage are intentionally deferred to T-060/the joint test phase requested by the user.
- Implemented T-053 as a lazy-loaded Preact `<support-agent>` custom element with a Shadow DOM style boundary, in-memory anonymous session custody, incremental SSE text/replacement/citation/completion handling, retry/error states, cancellation, responsive mobile behavior, accessible controls/live regions, and reduced-motion support.
- Added separate `loader.js` and `widget.js` production entries plus an automatic JSON bundle report. Widget lint, TypeScript, and production build pass; the baseline is 1.87 KB loader/25.56 KB widget raw and 10,965 bytes total gzip. Browser E2E remains deferred to T-060/the joint test phase.
- Implemented T-054 with persisted per-bot welcome text, accent color, and launcher position in migration `0011_widget_configuration`; added an owner/admin dashboard for exact allowed origins, publishable-key create/update/revoke, responsive preview, escaped generated loader snippet, clipboard flow, and installation guidance. Members remain read-only.
- T-054 targeted Ruff/web lint/type checks and seven focused bot/migration tests pass, including appearance round-trip. Live migration/browser E2E remains deferred to the joint test phase.
- Implemented T-055 owner/admin provider settings with transient write-only key forms, masked credential inventory, live verification, rotation, immediate revocation, verification/status timestamps, and ordered selection for platform-only, tenant-first with explicit fallback, or tenant-only routing. Member access is withheld and embedding/arbitrary URL controls remain excluded.
- T-055 web ESLint and TypeScript checks pass. Deterministic browser/API lifecycle coverage is scheduled in T-060; broad/live testing remains deferred per the user's batch instruction.
- Implemented T-060 Playwright coverage for registration → bot → file/website/manual ingestion → ready polling → cited playground answer → embedded widget chat, plus a second-tenant negative path. Added a credential-free deterministic BYOK browser lifecycle mock paired with the real T-046 backend security/routing suite, a local widget host, service orchestration, artifact paths, and execution documentation.
- Playwright discovers all three T-060 tests and the fixture server passes Node syntax validation. Per the user's explicit instruction, Chromium installation and actual service/browser execution are deferred until the later joint testing phase; `E2E_WEBSITE_URL` is intentionally required for a public SSRF-safe crawl fixture.
- Implemented T-061 reproducible multi-stage API/worker/migration, Next.js standalone, and static widget Docker images; a production Compose topology with private PostgreSQL/Redis, one-shot migrations, restricted runtime-role provisioning, health checks, persistent uploads, and loopback edge ports; plus secret-safe example configuration.
- Added an operations runbook covering deploy order, TLS/SSE proxying, secrets and BYOK custody, backups/restores, monitoring, rollback, incident response, hosting decisions, and a measured starting capacity floor for roughly 1,000 daily users. Runtime-role Ruff and web static checks pass. Docker is unavailable on this workstation, so image/Compose builds remain a production-test gate.
- Prepared the T-062 acceptance review with an evidence matrix, exact deferred gates, performance measurement plan, ten-step demo, known gaps/risks, Phase 2 priorities, and sign-off record. The review verdict is implementation-complete but not production-accepted; T-062 correctly remains unchecked until the user-requested joint full/live/browser/image/performance tests execute.
- Executed the local T-062 quality gate: Ruff, strict mypy over 113 files, 69 tests passed with 16 live-only skips, web/widget lint and typecheck, production web/widget builds, and the SQLite agent evaluation passed 6/6. GitHub Actions run `31160066729` separately passed all 85 live PostgreSQL/pgvector/Redis tests and the PostgreSQL evaluation 6/6 before its browser step failed at service startup.
- Fixed that browser startup failure by running root API/worker commands from `apps/api`. Added a production-Compose acceptance job covering image boot/health, restricted-role verification, 30-sample endpoint/chat measurements, isolated backup/restore, and immutable-tag service recovery, plus an executable performance report. These remote-only gates have not run yet, so T-062 remains unchecked.
- Completed T-062 on commit `c83d67a`: fixed standalone worker ORM registration, production Redis health quoting, dashboard same-origin normalization, conversational PostgreSQL lexical retrieval, and the classic widget loader contract uncovered by successive acceptance runs.
- Final GitHub Actions run `31212237732` passed both jobs: 86 live PostgreSQL/pgvector/Redis tests, 6/6 agent evaluation, 3/3 Playwright flows in 24.9 seconds, production image/Compose boot and health, restricted runtime-role verification, isolated dump/restore, and immutable-tag service recovery.
- The final 30-sample report measured endpoint p95 values at or below 6.01 ms, playground SSE total p95 at 26.68 ms, first-ready p95 at 10.58 ms, and manual-source ready time at 543.22 ms with deterministic providers. `docs/mvp-acceptance.md` records artifacts, gaps, demo, Phase 2 priorities, and the conditional production rollout decision.

### Session 17 — Codex

- Produced a 27-slide Relay team showcase covering the product problem, personas, complete feature map, architecture, technology choices, repository structure, tenant isolation, auth, ingestion, retrieval, grounded orchestration, provider routing, BYOK custody, streaming, UX, data model, API surface, acceptance evidence, measured performance, deployment, trade-offs, demo flow, gaps, and roadmap.
- Added the self-contained HTML source, an actual Relay product screenshot, a 27-page PDF, a 27-slide 16:9 PPTX, a reproducible PPTX builder, and a Bengali presenter guide with timing, demo checklist, and Q&A anchors.
- Rendered every slide in Microsoft Edge through Playwright, visually inspected all 27 slides in contact sheets plus a full-resolution clipping correction, and structurally verified both deliverables. The final PDF has 27 pages; the PPTX has 27 slides at 13.333 × 7.5 inches.

### Session 18 — Codex

- User promoted a Phase 2 provider-management expansion: a Hermes Agent-aligned provider catalog, guided dropdown setup, and custom generation-provider support. The work is split into T-071 through T-074 in `TASK2.md`; custom endpoints require explicit SSRF and secret-exfiltration defenses, while embedding BYOK remains excluded.
- User requested an account-info menu in place of the current direct logout controls. T-075 specifies an explicit sign-out action and accessible header/sidebar menu behavior.

### Session 19 — Codex

- Implemented T-070 social sign-in groundwork for Google, Microsoft, and GitHub while preserving email/password authentication. The server owns authorization-code exchange, PKCE, one-time Redis-backed state/continuations, OIDC nonce and issuer/audience validation, verified-email checks, provider/issuer/subject identity keys, organization setup/selection, and explicit authenticated account linking.
- Added the nullable password migration and global `provider_identities` table, typed API-client/BFF contracts, login/registration continuation UX, official inline provider marks, environment configuration, and authentication documentation. Apple and magic-link options remain excluded.
- Targeted Ruff, strict mypy, web lint/typecheck, 71 API tests (16 live-only skips), PostgreSQL offline migration SQL generation through `0012_social_auth`, and a production Next build all pass. Playwright inspected login at 1440×900 and 390×844; all three icon-only providers render with no horizontal overflow.
- T-070 remains unchecked until real provider credentials are configured and the live Google/Microsoft/GitHub callback paths are exercised in the joint acceptance environment.

### Session 20 - Codex

- Exercised the public Google callback on `relay.npcautomators.com` through the real OAuth consent flow. The callback initially exposed a missing `support_agent_app` grant on `provider_identities`.
- Added migration `0013_runtime_identity_grant`, kept its revision ID within PostgreSQL/Alembic's 32-character version limit, and added migration-head/grant assertions. Local Alembic, Ruff, mypy, and auth tests pass.
- Pushed commits `33ce90d` and `660e2a4`; the test VPS pulled `660e2a4`, applied the migration successfully, and restarted API/worker without replacing database volumes. Browser retest now reaches verified-social workspace setup; no API permission error remains.

### Session 21 - Codex

- User confirmed that Phase 2 is not complete and requested sequential completion of the remaining provider, account-menu, channel, and voice tasks.
- Added approved task T-078 for secure account deletion. The design releases the normalized email/provider identity after finalization so the same Gmail address can register a new account, while preventing orphaned workspaces, revoking sessions, and cleaning tenant-owned data safely.

### Session 22 - Codex

- Implemented T-071's Hermes-aligned provider catalog/setup experience. The catalog records the official source URL and captured Hermes `main` revision `6aaa181f0eb4dd517d9cf163733e7e41a8e126e1`, includes every listed provider, groups setup methods, exposes searchable provider/model dropdowns, and keeps OAuth/cloud/local/custom entries visibly unavailable until their secure adapters are ready.
- Added API catalog contracts, owner/admin isolation, maintained model entries, provider-specific approved OpenAI-compatible endpoints, expanded provider enum/migration `0014_provider_catalog_values`, and shared encrypted credential verification/routing for the ready API-key providers. Custom endpoint security remains in T-073; native OAuth/cloud/local adapters remain in T-072.
- Added catalog integrity, ready-provider credential lifecycle/routing, migration-head, Ruff/mypy, web lint/typecheck, and production-build coverage. Local focused suite passes 7 tests; the web lint/typecheck/build passes.
- Pushed commits `39f5f47` and `7f5886d` to `origin/main`. Test VPS pulled the commits, applied migration `0014_provider_catalog_values`, rebuilt with cache bypass, preserved existing volumes, and is healthy at `relay.npcautomators.com`. Live browser verification confirmed 20 ready providers, 20 clear coming-soon entries, provider/model switching, encrypted add, masked-only inventory, invalid-key status, and revoke cleanup. A stable test-only `BYOK_MASTER_KEY` was added to the VPS secret file and was not committed.

### Session 23 - Codex

- User established the development workflow: keep local work light, push source to GitHub, and run
  builds, database/integration suites, Playwright, and live-domain verification on the VPS.
- The VPS project was deliberately reset for development: application containers, project data
  volumes, and the old source checkout were removed; the repository was freshly cloned at
  `/opt/sp-version-2`, configured with new runtime secrets, and deployed behind the existing
  Cloudflare tunnel at `relay.npcautomators.com`. The fresh database started with no users or
  tenants. An old backup remains outside the live project under `/root/backups`.
- The account-menu layering and outside-click behavior fix was pushed and deployed in commit
  `7809298`.
- User required a new OTP on every registration and explicit login, including Google/social
  authentication. The agreed baseline is eight-character alphanumeric codes, 90-second expiry, keyed-hash storage,
  single use, replacement invalidation, bounded attempts, resend cooldown, and rate limits; no
  session is issued before verification.
- User selected personal Gmail SMTP for development and created a Google App Password named
  `Relay Development`. The secret remains private and must be entered directly into the VPS
  secret boundary, never chat, Git, browser storage, logs, or command history. Production will
  later move to a transactional provider without rewriting the auth flow.
- User also promoted a separate dynamic platform-admin dashboard. T-080 tracks mandatory OTP;
  T-081 tracks the least-privilege, audited platform-admin control plane and `/admin` UI. Work must
  proceed one planned and verified step at a time.
- Implemented the complete local T-080 password/social OTP flow. Pending authentication is stored
  in Redis, codes are stored only as keyed hashes, verification is atomic, and the dashboard BFF
  keeps challenge and continuation identifiers in `Secure`, `HttpOnly`, `SameSite=Lax` cookies.
  Registration creates no durable identity or session until OTP verification; explicit password
  and returning-social login issue no tokens until verification.
- Added provider-neutral authentication email delivery with Gmail STARTTLS configuration,
  professional HTML/plain-text messages, configuration validation, a test-only deterministic OTP,
  migration `0019_user_email_verification`, API/client/BFF/UI contracts, and focused API/E2E
  security coverage. T-080 remains unchecked until VPS integration, browser, and real email
  delivery acceptance pass.
- User changed the OTP expiry timer from ten minutes to 90 seconds. Backend expiry, API metadata,
  and dashboard countdown now use the same 90-second lifetime; the separate resend cooldown
  remains 60 seconds.

### Session 24 - Codex

- Diagnosed the reported Google registration failure with public Playwright and VPS evidence. The
  registration page sent `mode=register` correctly, but the backend ignored that stored OAuth mode;
  an already-linked Gmail identity could therefore silently enter login OTP and show "Welcome back."
- Fixed social mode preservation in commit `44d4987`. Register-mode callbacks now reject existing
  Relay identities with a clear sign-in instruction and do not issue a misleading login OTP. New
  social identities still continue through workspace setup and receive their registration OTP
  before any user, tenant, membership, provider identity, or session is created.
- OTP challenge metadata now includes the non-secret `register`/`login` flow, so pending signup UI
  always renders registration-specific copy. Social setup explicitly says that the fresh code is
  sent after the workspace name is submitted. Safe same-origin `next` paths now survive auth-mode
  switching, the provider round trip, and OTP verification in private short-lived cookies.
- Local auth tests pass (`20 passed`), with Ruff, focused strict mypy, web ESLint, and TypeScript
  clean. The VPS repeated the same 20 auth tests plus Ruff/mypy, built the production API/web
  images, and deployed `sp-version-2-44d4987` for API, worker, and web without touching the widget
  or Cloudflare tunnels.
- VPS Playwright passed desktop/mobile login, registration, social-registration copy, existing
  account messaging, Google register mode, safe `next`, and HttpOnly OAuth/pending cookies. A real
  Gmail plus-alias password registration reached the registration OTP screen and was immediately
  cancelled; database user/provider-identity counts remained unchanged. Three additional public
  auth UI rounds passed, production test OTP remains disabled, and recent API logs had no errors.

## 7. Open items

| ID | Item | Handling now |
|---|---|---|
| O1 | Hosting and budget | Use Docker and environment configuration; decide before production deployment |
| O2 | Platform model/embedding API keys and exact IDs | Use configuration and deterministic mocks if unavailable; optional tenant generation BYOK is scheduled in T-046/T-055 |
| O3 | Extra feature ideas | Wait for user; capture in `FEATURES.md` |
| O4 | Visual brand/design direction | Do not block backend/foundation work |

## HANDOFF STATE

**Last completed:** T-080 — mandatory email OTP for every registration and explicit login.
**Current task:** None; T-080 acceptance is complete.
**Next task:** T-081 — audited platform-admin control plane and dynamic `/admin` dashboard.
**Blocked on:** No implementation blocker. Production traffic remains blocked on hosting/budget selection and named release-owner/security approval of the prerequisites in `docs/mvp-acceptance.md`.

**Pushed state:** `origin/main` contains T-080 code commit `44d4987`; the VPS source is current and
API/worker/web run image tag `sp-version-2-44d4987` behind `relay.npcautomators.com`.
**Uncommitted work:** None. T-081 remains planning-only and may now begin when requested.
**Verification:** Local and VPS auth suites pass (`20 passed` each); Ruff, focused strict mypy,
web ESLint/TypeScript, production web build, public health, desktop/mobile Playwright, real Gmail
OTP initiation/cancel, safe redirect continuity, HttpOnly cookie boundaries, and three repeated UI
rounds pass. Production `AUTH_OTP_TEST_CODE` is disabled and recent API logs contain no errors.
**Gotchas:** Never request or print the Gmail App Password. SMTP/OTP secrets must not enter Git,
chat, browser storage, logs, process arguments, or shell history. No user/tenant/session may be
created before registration OTP verification, and no login/social session may be issued before its
OTP verification. `AUTH_OTP_TEST_CODE` is permitted only in an isolated `APP_ENV=test` stack and
must never be enabled in the live production stack.
