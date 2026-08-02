# Usage accounting

T-024 records normalized provider usage as immutable tenant events and exposes
a read-only summary at `GET /v1/usage/summary`. It measures usage for product
visibility only; quotas, plans, and billing enforcement remain deferred.

## Event units

Each event stores the tenant, optional historical bot and conversation IDs,
operation (`generation` or `embedding`), configured provider/model IDs, input
and output tokens, cache-read and cache-write tokens, latency in integer
milliseconds, and estimated cost in integer micro-USD.

Integer micro-USD avoids floating-point rounding in accounting. One US dollar
is `1_000_000` micro-USD. `total_tokens` is input plus output tokens; cache
counts are reported separately because provider cache metrics can overlap the
input count.

Provider adapters use `UsageRecordInput` and `UsageService.record(...)`. The
recorder flushes but deliberately does not commit, allowing future message and
usage persistence to share one transaction. It verifies that any supplied bot
belongs to the event tenant. Provider and model names remain configuration,
not hard-coded business logic.

## Append-only guarantees

The repository exposes insertion and aggregation but no update or delete
method. ORM update/delete hooks reject accidental mutation in local tests, and
the PostgreSQL migration installs a `BEFORE UPDATE OR DELETE` trigger for
database-level enforcement. There is no HTTP endpoint that creates, edits, or
deletes events.

Historical `bot_id` is intentionally not a foreign key: deleting a bot must
not erase its usage history. Tenant deletion is restricted while usage exists;
a future explicit retention/privacy workflow must handle any authorized purge
rather than relying on an accidental cascade.

## Summary API

Authenticated tenant members can call `GET /v1/usage/summary` with optional
`start`, `end`, and `bot_id` query parameters. Time boundaries require an
explicit timezone, are normalized to UTC, and use a half-open `[start, end)`
range. The response includes tenant totals and a provider/model/operation
breakdown with event count, token fields, latency, and estimated cost.

All summary queries repeat `tenant_id` predicates and run under forced RLS.
Cross-tenant bot filters return no events rather than widening the query.
