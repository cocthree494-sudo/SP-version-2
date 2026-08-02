# Bots and widget credentials

T-023 adds authenticated tenant dashboard APIs for bot configuration and
revocable public widget keys. Public widget chat and anonymous session tokens
remain part of T-044.

## Bot API

- `POST /v1/bots` creates a bot.
- `GET /v1/bots` lists only the authenticated tenant's bots.
- `GET /v1/bots/{bot_id}` returns one tenant-scoped bot.
- `PATCH /v1/bots/{bot_id}` updates supplied fields.
- `DELETE /v1/bots/{bot_id}` permanently deletes the bot and its keys.

Bot fields are `name`, optional `system_policy`, `default_language`, and
`status`. The language accepts `auto` or a normalized BCP 47-style tag. An
`active` bot can be resolved for public traffic; a `disabled` bot cannot.

Tenant owners and admins can create, change, and delete bots. Members can read
bot and key configuration but receive HTTP 403 for mutations. Cross-tenant IDs
return HTTP 404 rather than disclosing resource existence.

## Widget-key API

- `POST /v1/bots/{bot_id}/keys` creates a publishable key.
- `GET /v1/bots/{bot_id}/keys` lists key metadata.
- `PATCH /v1/bots/{bot_id}/keys/{key_id}` changes its label or origins.
- `DELETE /v1/bots/{bot_id}/keys/{key_id}` irrevocably revokes it.

Multiple active keys allow safe rotation: deploy a new key, then revoke the
old key. Revocation is idempotent, while a revoked key cannot be edited.

A publishable key is a public identifier, not a secret. It is intentionally
returned by list APIs so later embed instructions can be regenerated. Its
format contains a non-secret tenant UUID plus 256 bits of randomness. That
tenant address lets the unauthenticated widget boundary establish PostgreSQL
RLS before performing the exact key lookup. Future secret credentials must be
stored as hashes; this exception applies only to explicitly public keys.

Each key requires one to twenty exact allowed origins. Origins must use HTTP or
HTTPS and cannot contain credentials, paths, queries, fragments, or wildcards.
Scheme and host casing, IDN hostnames, IP literals, trailing `/`, and default
ports are canonicalized before storage and comparison. Empty allow-lists and
`*` are denied rather than interpreted as public access.

The reusable credential resolver validates key format, tenant scope, key
revocation, bot status, and exact normalized origin. T-044 will call this
resolver before issuing a short-lived anonymous widget session.

## Tenant isolation

Both `bots` and `bot_keys` carry `tenant_id`, use fail-closed repository
predicates, and have forced PostgreSQL row-level-security policies. A composite
foreign key from `(bot_keys.tenant_id, bot_keys.bot_id)` to
`(bots.tenant_id, bots.id)` also prevents a key from referencing another
tenant's bot even if application validation is bypassed.
