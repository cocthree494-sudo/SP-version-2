# Authentication

T-022 provides first-party dashboard authentication under `/v1`. It is a
JSON API; password reset, email verification, OAuth, and UI are intentionally
outside this task.

## Endpoints

- `POST /v1/auth/register` accepts `email`, `password`, `organization_name`,
  optional `display_name`, and optional `organization_slug`. It atomically
  creates the user, organization, owner membership, and first login session.
- `POST /v1/auth/login` accepts `email`, `password`, and optional
  `organization_slug`. A slug selects that organization when a user has more
  than one membership; without one, the earliest membership is selected.
- `POST /v1/auth/refresh` accepts `refresh_token` and returns a rotated access
  and refresh pair. A refresh credential can be used only once.
- `GET /v1/me` requires `Authorization: Bearer <access_token>` and returns the
  current user, selected organization, and live membership role.

Register returns HTTP 201. Login and refresh return HTTP 200. Token responses
contain `access_token`, `refresh_token`, `token_type: "bearer"`, and the access
token lifetime in `expires_in` seconds.

## Security behavior

Passwords are hashed with Argon2id. Login does equivalent password-hash work
for unknown identities and uses a generic credential error. Hashes can be
upgraded opportunistically on a successful login when Argon2 defaults change.

Access tokens are signed JWTs with issuer, audience, type, issued-at, expiry,
unique token ID, user ID, and tenant ID claims. The default lifetime is 15
minutes. Protected requests do not trust tenant claims alone: `/v1/me`
re-loads the active user, tenant, and tenant-scoped membership.

Refresh tokens are high-entropy opaque values. The tenant UUID in their prefix
is a non-secret address used to establish tenant RLS before lookup; only a
SHA-256 hash of the complete token is stored. Rotation locks the current row,
revokes it, and creates its replacement in one transaction. Reuse of a rotated
token revokes every still-active token in that family. A family's fixed expiry
defaults to 30 days and is not extended by rotation.

`refresh_tokens` is tenant-scoped by repository predicates and forced
PostgreSQL RLS. Login is the one pre-tenant operation: only after password
verification, a transaction-local `app.user_id` permits a SELECT-only policy
to read that user's own membership rows. It grants no membership writes or
access to another user's memberships.

## Configuration

Set `AUTH_JWT_SECRET` to a random value of at least 32 characters. Production
startup rejects a missing secret. Development and tests can use a process-local
ephemeral fallback, but a stable local value is included in `.env.example` so
tokens remain valid across application restarts and multiple workers.

The access and refresh lifetimes can be configured with
`AUTH_ACCESS_TOKEN_TTL_SECONDS` and `AUTH_REFRESH_TOKEN_TTL_DAYS`.
