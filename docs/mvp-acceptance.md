# MVP acceptance review

**Review date:** 2026-08-07  
**Scope:** Phase 1 tasks through T-061  
**Current verdict:** implementation-complete, **not yet production-accepted**

The vertical slice is implemented: tenant registration/auth, bot management,
file/website/manual knowledge ingestion, background parsing/chunking/embedding,
hybrid retrieval, grounded multilingual orchestration, conversation continuity,
usage summaries, secure optional generation BYOK, private playground, isolated
web widget, configuration/install UI, E2E coverage, and production definitions.

Acceptance cannot truthfully pass yet because the user requested broad testing,
browser execution, and production testing only after implementation. This review
therefore records exact evidence and makes the remaining gates executable rather
than treating an unrun check as a pass.

## Gate status

| Gate | Status | Evidence / next action |
|---|---|---|
| Phase 1 implementation through T-061 | Pass | Focused commits `627f626` through `ff93e0f` |
| T-046 BYOK focused security/lifecycle | Pass | Ruff plus 5 provider/migration tests |
| T-051–T-055 static frontend contracts | Pass | Web ESLint and TypeScript after each task |
| T-053 widget bundle | Pass | Loader 1.87 KB raw/997 B gzip; widget 25.56 KB raw/9,968 B gzip |
| T-054 bot/migration compatibility | Pass | 7 focused bot/migration tests plus appearance round-trip |
| T-060 test discovery | Pass | Playwright lists 3 tests; fixture server passes syntax validation |
| Full repository lint/type/unit suite | Pending | Run `npm run check` in the joint test phase |
| Live PostgreSQL/pgvector/Redis isolation after migrations 0010–0011 | Pending | Run CI integration matrix and schema parity against restricted role |
| Agent quality evaluation on current head | Pending | Run `npm run eval:agent` after live migration |
| Critical Playwright browser flow | Pending | Install Chromium, supply public `E2E_WEBSITE_URL`, run `npm run test:e2e` |
| Production image/Compose runtime | Pending | Docker unavailable on implementation workstation; build and boot in staging |
| Backup/restore and rollback drill | Pending | Follow `docs/operations.md` in isolated staging |
| Performance/load budgets | Pending | Measure the workload matrix below; no estimates may be reported as results |
| Production smoke/security review | Pending | TLS, SSE proxy, secrets/KMS, egress, alerts, canary, tenant isolation |

T-062 remains unchecked until every required pending gate either passes or is
explicitly waived by the release owner with a documented risk decision.

## Performance measurement matrix

The plan's budgets are measurement targets, not current claims:

- health/auth/list endpoints: p95 under 300 ms in the deployment region;
- hybrid retrieval: p95 under 500 ms at the agreed MVP corpus size;
- chat: measure time to `ready`, first text delta, completion, application
  overhead, and provider latency separately;
- ingestion: record upload acknowledgement, queue wait, parsing, chunking,
  embedding, and ready time by file size/source type;
- widget: preserve the 997-byte gzip lazy-loader baseline and review total bundle
  growth from 10,965 bytes gzip;
- capacity: test concurrent SSE sessions, PostgreSQL connections/IO, Redis queue
  latency/memory, worker throughput, crawler limits, and model cost.

Run cold and warm trials with small/medium/large tenant corpora, at least 30
samples per synchronous endpoint and a sustained load window for queues/streams.
Publish p50/p95/p99, errors, saturation, environment, dataset, provider mode, and
commit/image tag. Do not mix deterministic-provider application overhead with
live-provider latency results.

## Demo script for the complete slice

1. Register organization A and create an active support bot.
2. Add TXT/PDF or DOCX, a bounded public website, and an authoritative manual Q&A.
3. Show queued/processing/ready states and a safe source failure without request
   worker parsing.
4. Ask a supported question in the playground; show streaming, citations,
   retrieval state, conversation reset, and usage totals.
5. Ask an unsupported question and show the localized safe fallback.
6. Configure welcome/accent/position, create an exact-origin publishable key,
   copy the snippet, and chat through the Shadow DOM widget.
7. Attempt the same key from a wrong origin, then revoke it and show the existing
   anonymous session fail immediately.
8. Add a tenant generation key, prove only its last four characters return,
   verify it, select tenant-first with explicit fallback, rotate/reverify, revoke,
   and demonstrate the configured fallback behavior.
9. Sign into organization B and prove organization A's bot/source/conversation,
   usage, provider credential, and policy IDs return no data.
10. Show migration completion, restricted runtime DB role, health/readiness,
    worker queue, redacted structured logs, backup freshness, and image tags.

## Known gaps and risk decisions

- Docker images/Compose are authored but not built or booted on this workstation.
- The production object-storage implementation is still the local atomic volume
  adapter behind an S3-compatible interface. Multi-node worker deployment needs
  an actual private S3-compatible adapter and migration of existing objects.
- The local AES-GCM key wrapper is a KMS/Vault boundary, not a completed managed
  KMS integration. Safe wrapping-key rewrap tooling is not implemented.
- Generation BYOK supports only the fixed approved OpenAI endpoint; embedding
  BYOK and arbitrary base URLs are intentionally excluded. Platform redundancy
  is configuration-level, not yet real multi-provider production redundancy.
- The TypeScript client contracts are maintained manually rather than generated
  and diff-checked from FastAPI OpenAPI.
- Metrics/exporter dashboards and alert integrations are specified but not wired
  to a selected hosting vendor.
- No billing, quotas, plan enforcement, platform-admin tooling, human inbox, or
  channel adapters beyond the web widget are in Phase 1.
- Malware scanning, managed object versioning, data-residency policy, DPA/legal
  review, accessibility audit, and external penetration testing need production
  decisions before sensitive customer traffic.

## Proposed Phase 2 priorities (not implemented)

1. Close release infrastructure gaps: managed S3 adapter, KMS wrapping/rewrap,
   OpenAPI contract generation, metrics/alerts, and automated staging acceptance.
2. Add real provider redundancy with provider-neutral health/cost policy and
   tenant-visible routing audit, preserving explicit fallback consent.
3. Add tenant analytics for retrieval quality, deflection, latency, usage/cost,
   source freshness, and failure investigation.
4. Add requested channel adapters (Telegram, WhatsApp, Messenger, email) around
   the existing channel-neutral core, with channel-specific consent/security.
5. Design consent-aware durable customer memory with view/correct/delete,
   retention, residency, and per-channel identity linking before implementation.
6. Move billing/quotas and human handoff/inbox into Phase 3 after reliability and
   analytics reveal real operating costs and escalation needs.

## Sign-off record

Record the acceptance environment, commit and immutable image tags, test/eval
artifact links, performance report, restore drill, known-risk waivers, release
owner, security reviewer, and date here after the pending gates run. Until then,
the correct release decision is **no production customer traffic**.
