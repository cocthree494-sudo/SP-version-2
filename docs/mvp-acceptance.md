# MVP acceptance review

**Review date:** 2026-08-07  
**Scope:** Phase 1 tasks through T-062
**Current verdict:** **MVP technical acceptance passed; production rollout remains conditional**

The Phase 1 vertical slice is complete: tenant registration/auth, bot management,
file/website/manual ingestion, background parsing/chunking/embedding, hybrid
retrieval, grounded multilingual orchestration, conversation continuity, usage
summaries, optional generation BYOK, private playground, isolated widget,
configuration/install UI, E2E coverage, and production definitions.

The full local quality gate and remote restricted-role, browser, production
Compose, recovery, and deterministic performance gates pass. This accepts the
implementation and staging-style deployment artifact. It does not authorize
production customer traffic: hosting, managed storage/KMS, TLS edge, monitoring,
legal/security review, and named release-owner sign-off remain prerequisites.

## Gate status

| Gate | Status | Evidence / decision |
|---|---|---|
| Phase 1 implementation through T-061 | Pass | Focused commits `627f626` through `ff93e0f` |
| T-046 BYOK security/lifecycle | Pass | Focused provider/migration suite plus final live suite |
| T-051–T-055 frontend contracts | Pass | Web ESLint and TypeScript after each task and in final CI |
| T-053 widget bundle | Pass | Classic loader 996 B raw/571 B gzip; widget 25,560 B raw/9,968 B gzip; 10,539 B total gzip |
| T-054 bot/migration compatibility | Pass | Appearance round-trip and migration coverage pass |
| Full repository lint/type/unit suite | Pass | Local `npm run check`: Ruff, strict mypy over 114 files, 70 tests passed/16 live-only skipped, web/widget lint and typecheck |
| Live PostgreSQL/pgvector/Redis isolation | Pass | Run `31212237732`: restricted role and all 86 tests passed, including conversational retrieval and cross-tenant coverage |
| Agent quality evaluation | Pass | Run `31212237732` passed PostgreSQL evaluation 6/6; local SQLite evaluation passed 6/6 |
| Critical Playwright browser flow | Pass | Run `31212237732`: 3/3 tests in 24.9 s—BYOK lifecycle, cited ingestion/playground/widget path, and second-tenant negative path |
| Production image/Compose runtime | Pass | Run `31212237732` built and booted all services and passed health/readiness checks |
| Backup/restore and recovery drill | Pass | Restored a custom dump into `support_agent_restore`, verified its migration version, and recovered services from immutable tag `acceptance` |
| Deterministic performance budgets | Pass | 30 warm samples; every synchronous p95 below 7 ms, chat total p95 26.68 ms, manual ingestion ready in 543.22 ms |
| Production rollout review | Conditional | Technical smoke/isolation pass; selected-host TLS/SSE edge, managed S3/KMS, alerts, canary, legal/security review, and human sign-off remain mandatory |

## Execution record

- Final evidence is GitHub Actions run `31212237732` on commit
  `c83d67a9a53627d20c2befc4eb95625f30a2feb8`; both `lint-and-test` and
  `Production Compose acceptance` completed successfully.
- The live gate applied all migrations, configured the non-owner/non-superuser
  application role, passed 86 tests and the 6/6 PostgreSQL agent evaluation,
  then completed all three Playwright scenarios.
- The production gate built and booted the Compose topology, verified runtime
  role and health, generated `acceptance-performance.json`, restored a dump into
  an isolated database, and restarted application services from the current tag.
- Acceptance artifacts are
  `playwright-acceptance-c83d67a9a53627d20c2befc4eb95625f30a2feb8`
  (artifact `9007185594`) and
  `production-acceptance-c83d67a9a53627d20c2befc4eb95625f30a2feb8`
  (artifact `9007173964`).
- Successive acceptance runs exposed and fixed real runtime defects in the API
  BFF origin check, Redis health command, worker ORM startup, PostgreSQL lexical
  retrieval, and classic widget loader. The final run proves all fixes together.

## Performance results

Run `31212237732` measured the production Compose topology on a hosted GitHub
runner with deterministic providers:

| Path | Samples | p50 | p95 | p99 |
|---|---:|---:|---:|---:|
| Liveness | 30 | 2.05 ms | 3.05 ms | 5.39 ms |
| Readiness | 30 | 2.97 ms | 3.33 ms | 3.45 ms |
| Authenticated `/me` | 30 | 4.91 ms | 5.39 ms | 6.51 ms |
| Bot list | 30 | 5.50 ms | 6.01 ms | 7.11 ms |
| Playground SSE chat, total | 30 | 22.44 ms | 26.68 ms | 56.75 ms |

Chat first-ready p95 was 10.58 ms. Manual source creation through worker
processing and ready state took 543.22 ms. Chat timing includes retrieval,
deterministic generation, persistence, and SSE delivery, so it demonstrates the
application-path budget but is not a live-provider latency claim.

Before production sizing, repeat cold and warm trials with small/medium/large
tenant corpora and live approved providers. Add sustained concurrency for SSE,
PostgreSQL connections/IO, Redis latency/memory, worker throughput, crawler
limits, error rates, saturation, and model cost.

## Demo script for the complete slice

1. Register organization A and create an active support bot.
2. Add TXT/PDF or DOCX, a bounded public website, and authoritative manual Q&A.
3. Show queued/processing/ready states and a safe source failure without request-worker parsing.
4. Ask a supported question in the playground; show streaming, citations, retrieval state, reset, and usage.
5. Ask an unsupported question and show the localized safe fallback.
6. Configure appearance, create an exact-origin publishable key, copy the snippet, and chat through the Shadow DOM widget.
7. Attempt the key from a wrong origin, then revoke it and prove the anonymous session fails.
8. Add a tenant generation key; prove masking, verify, explicit fallback, rotate/reverify, and revoke.
9. Sign into organization B and prove organization A's tenant-owned identifiers return no data.
10. Show migrations, restricted runtime role, readiness, worker queue, redacted logs, restore evidence, and image tags.

## Known gaps and risk decisions

- Production Compose is proven in hosted CI; this workstation lacks Docker, so
  future image/runtime regressions continue to rely on the remote gate.
- Object storage remains the local atomic volume adapter behind an S3-compatible
  boundary. Multi-node production requires a private managed adapter and object migration.
- The local AES-GCM key wrapper is a KMS/Vault boundary, not managed KMS; safe
  wrapping-key rewrap tooling is not implemented.
- Generation BYOK supports only the approved OpenAI endpoint. Embedding BYOK and
  arbitrary base URLs remain intentionally excluded; platform redundancy still
  requires real provider configuration.
- TypeScript client contracts are maintained manually rather than generated and
  diff-checked from FastAPI OpenAPI.
- Metrics/exporter dashboards and alerts are specified but not connected to a
  selected host. Billing, quotas, platform admin, human inbox, and non-widget
  channel adapters are outside Phase 1.
- Malware scanning, managed object versioning, data residency, DPA/legal review,
  accessibility audit, and external penetration testing remain production decisions.

## Proposed Phase 2 priorities (not implemented)

1. Close release infrastructure gaps: managed S3 adapter, KMS wrapping/rewrap,
   OpenAPI contract generation, metrics/alerts, and automated staging acceptance.
2. Add real provider redundancy with provider-neutral health/cost policy and
   tenant-visible routing audit while preserving explicit fallback consent.
3. Add tenant analytics for retrieval quality, deflection, latency, usage/cost,
   source freshness, and failure investigation.
4. Add requested channel adapters around the channel-neutral core with
   channel-specific consent and security.
5. Design consent-aware durable customer memory with view/correct/delete,
   retention, residency, and per-channel identity linking before implementation.
6. Defer billing/quotas and human handoff/inbox until reliability and analytics
   establish real operating costs and escalation needs.

## Sign-off record

- **Technical acceptance:** pass on 2026-08-07 in GitHub Actions Ubuntu runners,
  run `31212237732`, commit
  `c83d67a9a53627d20c2befc4eb95625f30a2feb8`, image tag `acceptance`.
- **Evidence:** artifacts `9007185594` and `9007173964`; 86 live tests, 6/6
  evaluation cases, 3/3 browser scenarios, performance report, isolated restore,
  and immutable-tag recovery all passed.
- **Release decision:** Phase 1 implementation and staging deployment are
  technically accepted. Production customer traffic remains **no-go** until a
  release owner and security reviewer approve the selected-host edge, managed
  storage/KMS, monitoring/alerts, legal requirements, and known risks.
- **Human sign-off:** release owner and security reviewer are not yet supplied;
  this is a deployment prerequisite, not unfinished T-062 implementation work.
