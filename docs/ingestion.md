# Storage and ingestion foundations

T-030 establishes durable, tenant-scoped boundaries used by the file, website,
manual, parser, embedding, and retrieval tasks documented in
[Knowledge ingestion and retrieval](knowledge.md).

## Object storage

`ObjectStorage` is a streaming provider interface. Every method receives an
explicit tenant UUID and a logical relative POSIX key. Implementations must map
that pair to a tenant-prefixed object and reject absolute paths, traversal,
backslashes, and non-canonical keys.

Development uses `LocalObjectStorage`, rooted at `LOCAL_STORAGE_ROOT`. Writes go
to a temporary file and are atomically replaced only after the stream finishes;
failed writes remove the temporary file. The `S3CompatibleObjectStorage` marker
documents the same contract for a future S3, R2, or MinIO adapter without
introducing a production vendor now.

## Durable records

- `knowledge_sources` owns bot-level file, website, or manual configuration and
  user-visible processing status.
- `documents` stores version, checksum, source metadata, raw/normalized storage
  references, and staged/active/superseded/failed state. Activating a version
  supersedes the previous active version instead of deleting it.
- `ingestion_jobs` stores the operation, stable idempotency key, attempt counts,
  progress, schedule, safe error fields, and terminal state.

All three tables carry `tenant_id`, use composite tenant foreign keys, repeat
tenant predicates in repositories, and have forced PostgreSQL RLS policies.

## Queue and retry conventions

The API transaction commits an `ingestion_jobs` row before dispatching the
minimal `{tenant_id, job_id}` message to Redis. ARQ uses
`ingestion:<tenant_id>:<job_id>` as its queue-level job ID, so repeated dispatch
does not duplicate live work. A recovery dispatcher can re-enqueue committed
queued jobs after a Redis outage.

The worker claims a database job under tenant scope, increments its attempt,
and commits before calling a registered handler. Classified permanent failures
fail immediately. Retryable and unexpected failures use capped exponential
backoff configured by `INGESTION_RETRY_BASE_SECONDS`,
`INGESTION_RETRY_MAX_SECONDS`, and `INGESTION_MAX_ATTEMPTS`. Unexpected exception
details are logged internally; only a safe generic error is stored for users.

Run the worker independently with:

```powershell
npm run dev:worker
```

The normal `npm run dev` flow starts the API, worker, dashboard, and widget.
Parsing, crawling, and embedding handlers run only in the worker, never inside
API request workers.
