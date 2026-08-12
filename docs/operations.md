# Production operations runbook

This runbook is the T-061 release baseline for the API, ingestion worker,
dashboard, widget assets, PostgreSQL/pgvector, Redis, and tenant-upload storage.
It describes the included single-host Compose topology; managed equivalents are
preferred when the operating team can support them.

## Images and process separation

- `apps/api/Dockerfile` produces one non-root, lockfile-frozen Python image. The
  same digest runs the API, one-shot migrations, restricted-role provisioning,
  and ARQ worker so code and schema tooling cannot drift.
- `apps/web/Dockerfile` produces a non-root Next.js standalone image with public
  API/widget URLs fixed at build time. Runtime server-to-server requests use the
  private `API_INTERNAL_URL`.
- `packages/widget/Dockerfile` builds the measured Preact assets and serves them
  from Nginx with CORS, nosniff, and short cache headers. Versioned CDN filenames
  are a later optimization; deploy API and widget compatibly while names remain
  stable.
- API and worker are separate processes. Parsing, crawling, and embedding never
  run in API request workers. Migrations are a one-shot dependency and must
  complete before application processes start.

The root `.dockerignore` excludes Git metadata, secrets, dependencies, caches,
uploads, AI-local settings, and test artifacts from every image context.

## First deployment

1. Copy `.env.production.example` to `.env.production` outside source control.
   Generate independent high-entropy PostgreSQL owner, PostgreSQL app-role,
   Redis, and 64+ character JWT secrets. URL-encode passwords inside URLs.
2. Decide public HTTPS names for dashboard, API, and widget host. Set
   `PUBLIC_API_URL` and `PUBLIC_WIDGET_LOADER_URL` before building the web image.
   If social sign-in is enabled, set `OAUTH_WEB_BASE_URL` to the dashboard origin
   and register the exact callback paths
   `/api/auth/oauth/google/callback`, `/api/auth/oauth/microsoft/callback`, and
   `/api/auth/oauth/github/callback` with the corresponding providers. Leave a
   provider's client ID and secret blank to keep that provider disabled.
3. For tenant BYOK, create a URL-safe-base64 32-byte wrapping key in KMS/Vault or
   the deployment secret manager and set `BYOK_MASTER_KEY` plus a stable version.
   Database operators should not have access to this key. Leave it unset only if
   BYOK endpoints are intentionally unavailable.
4. Replace deterministic provider settings with approved production generation
   and embedding provider configuration. Model IDs and secrets remain env/secret
   configuration; never bake them into images.
5. Build from a clean commit and immutable tag:

   ```text
   docker compose --env-file .env.production -f infra/compose.production.yaml build
   docker compose --env-file .env.production -f infra/compose.production.yaml up -d
   ```

6. Put a TLS reverse proxy/load balancer in front of loopback-bound ports. Route
   dashboard to 3000, API to 8000, and widget assets to 8080. Preserve streaming,
   disable proxy buffering for `text/event-stream`, and set an upstream timeout
   above `MODEL_ROUTER_TOTAL_TIMEOUT_SECONDS`.
7. Inspect `migrate` exit status, `/health/live`, `/health/ready`, dashboard
   login, worker health, widget `/health`, and one grounded canary conversation.
   Do not expose PostgreSQL or Redis ports publicly.

`migrate` connects as the schema owner, applies Alembic, sets the separately
supplied `support_agent_app` password using safely quoted SQL, and verifies that
the runtime role is non-superuser/NOBYPASSRLS. API and worker connect only through
`APP_DATABASE_URL`; using the owner URL in either process defeats the RLS safety
model and is a release blocker.

## Secrets and credential rotation

- Supply `.env.production` from a deployment secret store when possible. Never
  commit it, print it in CI, place it in image layers, or expose it to the web
  build except the two explicitly public URL arguments.
- Rotate the JWT secret with a planned forced logout; the current implementation
  has one active signing key and no overlapping key ring.
- Rotate Redis/app-role passwords by updating the secret store, rerunning the
  role provisioner for the app role, and rolling API/worker processes.
- BYOK wrapping-key rotation requires decrypting the old key version while
  rewrapping every data key. Do not simply replace `BYOK_MASTER_KEY_VERSION`;
  current envelopes fail closed when their version is unavailable. KMS migration
  tooling is required before that rotation.
- Tenant raw provider keys must never appear in logs, traces, job payloads,
  prompts, browser storage, shared caches, support tickets, or plaintext backups.

## Backups and restore drills

Back up three independent stores on an encrypted schedule:

1. PostgreSQL with a managed snapshot plus daily logical `pg_dump --format=custom`.
2. The upload volume/object store with tenant prefixes and object versioning.
3. Redis AOF only for short-lived operational recovery; PostgreSQL and object
   storage remain authoritative.

Keep the BYOK wrapping key outside database backups. A database dump alone must
not decrypt tenant keys. Encrypt backup media, restrict restore permissions, set
retention, and record checksums. At least quarterly, restore into an isolated
network, apply the same image tag, run Alembic to the expected revision, verify
object/document references, test a restricted-role cross-tenant denial, and send
a deterministic grounded canary. Record RPO/RTO from the drill.

Before schema changes or releases, take a fresh database snapshot and confirm an
object-store restore point. Never test restores over production data paths.

## Health, monitoring, and alerts

- `/health/live`: process liveness only.
- `/health/ready`: PostgreSQL and Redis readiness; remove an instance from load
  balancing on 503.
- Worker: process health plus queue age, pending/failed ingestion jobs, retry
  counts, and oldest job latency.
- Product: API error/latency percentiles, SSE disconnects, model retry/failover,
  circuit opens, tenant-only unavailable errors, usage cost, crawl failures,
  database saturation, Redis memory, disk/object capacity, and backup age.

Logs should be structured and correlated, but avoid customer prompts/source
content and all credentials. Alert on cross-tenant/RLS errors, repeated auth
failures, provider authentication spikes, readiness failures, queue backlog,
backup failure, disk pressure, and abnormal cost growth.

## Rollout and rollback

1. Deploy the migration/image to staging and run the acceptance gates.
2. Snapshot data, run the one-shot migration, deploy worker, then API/web/widget.
3. Use a canary API instance if supported; compare errors, latency, retrieval
   quality, and costs before full traffic.
4. Roll application containers back by immutable image tag only when previous
   code is forward-compatible with the migrated schema. Migrations in this MVP
   are additive, but compatibility must be reviewed release by release.
5. Do not automatically run Alembic downgrade on production. If a migration is
   faulty and not forward-compatible, stop writes, restore the verified
   pre-release snapshot/object restore point, then deploy the previous tag.

Document incident timestamps, affected tenants, data exposure assessment,
recovery actions, and follow-up. A suspected BYOK-key disclosure requires tenant
notification and provider-side key revocation, not only an application rollback.

## Hosting decision checklist

Choose hosting only after answering:

- Are API and worker independently scalable, with SSE-compatible load balancing?
- Are managed PostgreSQL pgvector, point-in-time recovery, restricted roles, and
  tested restores available?
- Can Redis be private, authenticated, persistent enough for queue recovery, and
  monitored for eviction?
- Is tenant object storage private, encrypted, versioned, lifecycle-managed, and
  malware-scannable?
- Can secrets/KMS access be separated from database administration and audited?
- Are outbound provider/crawler egress, fixed public HTTPS domains, CDN CORS, log
  redaction, regional residency, and incident response supported?
- What are hard monthly budgets and scale triggers for tokens, storage, crawling,
  queue depth, API latency, and concurrent SSE connections?

For an initial roughly 1,000 daily users (not 1,000 simultaneous chats), start
measurement around two API replicas at 1 vCPU/1–2 GB each, one 2 vCPU/2–4 GB
worker, a 2 vCPU/4 GB managed PostgreSQL instance with at least 50 GB and PITR,
an authenticated 1 GB Redis, object storage, and a small web/widget tier. This is
a planning floor, not a guarantee: load-test actual message rate, document size,
embedding throughput, model latency, and concurrent streams before production.
Scale workers on queue age, API on concurrent requests/SSE latency, and database
on measured CPU/IO/connections—not account count alone.
