# Execution Tasks

This file is the source of truth for implementation order. If the user says only **“continue”**, take the first unchecked task whose dependencies are complete. Work on one task at a time unless the user explicitly asks for a broader batch.

Completion means implementation, proportionate tests/checks, documentation/handoff updates, and no known in-scope defect. Do not check a task merely because files were created.

## Completed setup

- [x] **T-000 — Product discovery and architecture baseline**  
  Output: project decisions, scope, phases, and initial architecture.

- [x] **T-001 — Cross-agent handoff and Git foundation**  
  Depends on: T-000  
  Output: detailed plan, granular tasks, agent instructions, feature inbox, context handoff, Git repository/remote/initial commit.

## Phase 1A — Repository foundation

- [x] **T-010 — Scaffold monorepo and local development stack**  
  Depends on: T-001  
  Create `apps/api`, `apps/web`, `packages/widget`, shared configuration, `.env.example`, and Docker Compose for PostgreSQL/pgvector and Redis. Add one-command development instructions. No product UI yet.

- [x] **T-011 — Add quality gates and CI baseline**  
  Depends on: T-010  
  Backend lint/type/test commands, frontend lint/type/test commands, pre-commit or equivalent, and GitHub Actions that run the same commands.

- [x] **T-012 — Add configuration, logging, and health endpoints**  
  Depends on: T-010  
  Typed environment settings, secret-safe structured logging, request IDs, `/health/live`, `/health/ready`, and DB/Redis readiness checks.

## Phase 1B — Tenancy, auth, and usage

- [x] **T-020 — Create database base and first migration**
  Depends on: T-010  
  Async SQLAlchemy session, Alembic, UUID/time conventions, pgvector extension, and shared model mixins.

- [x] **T-021 — Implement tenants, users, memberships, and isolation**
  Depends on: T-020  
  Tables/repositories for users, tenants, memberships/roles; explicit tenant context and row-level-security strategy. Include cross-tenant isolation tests.

- [x] **T-022 — Implement minimal authentication**
  Depends on: T-021  
  Register/login/refresh/me, Argon2id password hashing, rotated refresh tokens, and bootstrap organization creation. No password reset/email verification UI unless separately tasked.

- [x] **T-023 — Implement bots and public widget credentials**
  Depends on: T-021  
  Bot CRUD, revocable publishable keys, allowed origins, status, and tenant-scoped tests.

- [ ] **T-024 — Implement append-only usage events**  
  Depends on: T-021  
  Normalized token/latency/cost records and a basic tenant summary endpoint; no billing enforcement.

## Phase 1C — Knowledge ingestion and retrieval

- [ ] **T-030 — Add storage and ingestion job abstractions**  
  Depends on: T-020, T-021  
  Local storage adapter, S3-compatible interface, knowledge source/document/job tables, Redis worker, idempotency and retry conventions.

- [ ] **T-031 — Add secure file upload source**  
  Depends on: T-023, T-030  
  PDF/DOCX/TXT/MD upload, type/size validation, checksum, source status, and storage cleanup behavior.

- [ ] **T-032 — Add text extraction and normalization**  
  Depends on: T-031  
  Parsers for supported formats, metadata/title extraction, deterministic normalized output, error reporting, and parser fixtures.

- [ ] **T-033 — Add chunking and embedding pipeline**  
  Depends on: T-032  
  Structural chunking, token limits/overlap, embedding provider interface plus deterministic test provider, batch persistence, version activation, and retry tests.

- [ ] **T-034 — Add bounded website crawler source**  
  Depends on: T-030, T-033  
  Same-domain bounded crawl, canonicalization, useful-text extraction, robots/rate controls, SSRF/redirect defense, deduplication, and progress status.

- [ ] **T-035 — Add manual Q&A source**  
  Depends on: T-023, T-033  
  Create/edit/delete authoritative Q&A entries and re-embed changed entries.

- [ ] **T-036 — Implement tenant-scoped hybrid retrieval**  
  Depends on: T-033  
  Vector + lexical search, filters, score fusion, deduplication, citation metadata, and retrieval/isolation evaluation fixtures.

## Phase 1D — Core support agent

- [ ] **T-040 — Create provider-neutral LLM and embedding adapters**  
  Depends on: T-012  
  Normalized request/stream/usage/error types, configurable provider implementation, deterministic mock, timeouts, and secret-safe tests.

- [ ] **T-041 — Add model tiering and failover router**  
  Depends on: T-040  
  Low-cost default, promotion rules, bounded retry, provider health/circuit state, routing reason, and failure simulations. A second paid provider is not required yet.

- [ ] **T-042 — Implement conversations, messages, and compaction**  
  Depends on: T-021, T-023, T-040  
  Conversation/message schema, recent-window loading, rolling summary interface, retention hooks, and tenant isolation tests.

- [ ] **T-043 — Implement grounded RAG answer orchestration**  
  Depends on: T-024, T-036, T-041, T-042  
  Retrieval, prompt assembly, multilingual rule, citations, uncertainty fallback, prompt-injection boundaries, message persistence, and usage recording.

- [ ] **T-044 — Add streaming chat API and anonymous widget sessions**  
  Depends on: T-043  
  SSE stream, cancellation/disconnect handling, publishable-key/origin validation, short-lived anonymous sessions, and rate limiting.

- [ ] **T-045 — Add agent quality and safety evaluation set**  
  Depends on: T-043  
  Grounding, refusal/fallback, multilingual, citation, prompt-injection, and cross-tenant scenarios with repeatable pass/fail reporting.

## Phase 1E — Dashboard and widget

- [ ] **T-050 — Build dashboard shell and auth flow**  
  Depends on: T-022  
  Fast responsive Next.js shell, login/register, protected routes, organization context, error/loading states, and accessible design tokens.

- [ ] **T-051 — Build bot and knowledge-management UI**  
  Depends on: T-023, T-031, T-034, T-035, T-050  
  Bot CRUD, drag/drop files, website/manual forms, source list/status/errors, polling or events, and deletion confirmation.

- [ ] **T-052 — Build tenant playground and usage summary**  
  Depends on: T-024, T-043, T-050  
  Streaming chat, visible citations/retrieval state where appropriate, reset conversation, and basic usage view.

- [ ] **T-053 — Build isolated embeddable web widget**  
  Depends on: T-044  
  Preact custom element, lazy loader, Shadow DOM or equivalent CSS isolation, responsive/accessibility behavior, streaming, retry/error states, and bundle-size report.

- [ ] **T-054 — Add widget configuration and embed instructions**  
  Depends on: T-051, T-053  
  Basic theme/welcome text, allowed origins, generated snippet, preview, and copyable installation instructions.

## Phase 1F — MVP verification and handoff

- [ ] **T-060 — Add critical-path end-to-end tests**  
  Depends on: T-045, T-051, T-052, T-054  
  Register → create bot → ingest each source type → ask grounded question → embed/widget chat. Include a cross-tenant negative path.

- [ ] **T-061 — Add production Docker build and operations runbook**  
  Depends on: T-060  
  Reproducible images, migrations, worker/web processes, backups, secrets, health checks, rollback, and hosting decision checklist.

- [ ] **T-062 — MVP acceptance review**  
  Depends on: T-061  
  Run tests/evaluations, measure performance budgets, document known gaps, demo the complete slice, and propose Phase 2 priorities without implementing them.

## Later task buckets — not yet scheduled

- Phase 2: real multi-provider redundancy, channel adapters, analytics, consent-aware durable memory.
- Phase 3: Stripe/business layer, platform admin, human handoff.
- Phase 4: growth analytics, voice, approved auto-learning.

Do not convert these buckets into implementation silently. Break them into task IDs when the user promotes that phase.
