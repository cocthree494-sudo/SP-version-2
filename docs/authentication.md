# Authentication

T-022 provides first-party dashboard authentication under `/v1`. T-080 adds a
mandatory email OTP before every registration and explicit login. Social sign-in
is available for Google, Microsoft, and GitHub when their server-side credentials
are configured; Apple and magic links are not enabled.

## Endpoints

- `POST /v1/auth/register` accepts `email`, `password`, `organization_name`,
  optional `display_name`, and optional `organization_slug`. It returns a
  short-lived OTP challenge; no user, organization, membership, or session exists
  until that challenge is verified.
- `POST /v1/auth/login` accepts `email`, `password`, and optional
  `organization_slug`. A slug selects that organization when a user has more than
  one membership. A fresh OTP challenge is required before a session is issued.
- `POST /v1/auth/otp/status` returns non-secret challenge metadata.
- `POST /v1/auth/otp/resend` replaces the previous code after the cooldown.
- `POST /v1/auth/otp/cancel` removes a pending challenge.
- `POST /v1/auth/otp/verify` consumes the single-use code and returns the normal
  access/refresh pair only after the pending operation succeeds.
- `POST /v1/auth/refresh` accepts `refresh_token` and returns a rotated access and
  refresh pair. A refresh credential can be used only once.
- `GET /v1/me` requires `Authorization: Bearer <access_token>` and returns the
  current user, selected organization, and live membership role.
- `POST /v1/auth/oauth/{provider}/start` creates a short-lived, one-time PKCE
  state and returns the provider authorization URL.
- `POST /v1/auth/oauth/{provider}/callback` validates the state, exchanges the
  code on the server, verifies the provider identity, and returns either a fresh
  OTP challenge or a one-time organization/account-link continuation. It never
  returns a normal session.
- `POST /v1/auth/oauth/register` completes a new social user's workspace setup and
  starts the required OTP challenge.
- `POST /v1/auth/oauth/select` selects an organization for a linked social user and
  starts the required OTP challenge.
- `POST /v1/auth/oauth/link` links a verified provider identity only from an
  authenticated password account; matching email alone never links.

Register returns HTTP 202 with challenge metadata. Login returns HTTP 200 with
challenge metadata. OTP verification and refresh return HTTP 200 token responses
containing `access_token`, `refresh_token`, `token_type: "bearer"`, and the access
token lifetime in `expires_in` seconds.

Challenge metadata includes a non-secret `flow` value (`register` or `login`) so
the dashboard keeps registration copy for a pending signup even if the user
reopens a different auth URL. OAuth also preserves a safe same-origin `next`
path through the provider redirect and OTP step. A social flow started in
registration mode never silently becomes a login: an already-linked provider
identity or matching email returns a registration conflict with a clear sign-in
instruction and does not send an OTP.

## Security behavior

Passwords are hashed with Argon2id. Login does equivalent password-hash work for
unknown identities and uses a generic credential error. Hashes can be upgraded
opportunistically after a successful OTP when Argon2 defaults change.

Access tokens are signed JWTs with issuer, audience, type, issued-at, expiry,
unique token ID, user ID, and tenant ID claims. The default lifetime is 15
minutes. Protected requests do not trust tenant claims alone: `/v1/me` re-loads
the active user, tenant, and tenant-scoped membership.

Refresh tokens are high-entropy opaque values. The tenant UUID in their prefix is
a non-secret address used to establish tenant RLS before lookup; only a SHA-256
hash of the complete token is stored. Rotation locks the current row, revokes it,
and creates its replacement in one transaction. Reuse of a rotated token revokes
every still-active token in that family. A family's fixed expiry defaults to 30
days and is not extended by rotation.

`refresh_tokens` is tenant-scoped by repository predicates and forced PostgreSQL
RLS. Login is the one pre-tenant operation: only after password verification, a
transaction-local `app.user_id` permits a SELECT-only policy to read that user's
own membership rows. It grants no membership writes or access to another user's
memberships.

Social identity records are keyed by `(provider, issuer, subject)`, never by email
alone. Google and Microsoft use authorization-code + PKCE with an OIDC nonce and
server-side identity-token validation; GitHub uses server-side authorization-code
exchange and a verified primary email. OAuth state and continuation tokens are
one-time values stored in Redis with a short TTL. Client secrets and provider
tokens never reach the browser. Every social registration and login still
requires the fresh email OTP before a session or identity record is finalized.

## OTP security

Codes are eight-character alphanumeric values, expire after 90 seconds, are stored only as an HMAC keyed
by `AUTH_OTP_SECRET`, and are consumed atomically. A wrong code consumes one of
five attempts; the challenge is locked after the final failure. Resending resets
the attempts and invalidates the previous code. Email and IP request windows plus
the resend cooldown limit abuse. Pending payloads, password hashes, raw codes,
SMTP credentials, and OAuth tokens never appear in API responses or logs.

The dashboard BFF keeps only an opaque pending challenge identifier in a Secure,
`HttpOnly`, `SameSite=Lax` cookie. Browser JavaScript receives neither the
challenge identifier nor any access/refresh token. Starting over cancels the
server-side challenge as well as clearing the cookie.

## Configuration

Set `AUTH_JWT_SECRET` and a separate `AUTH_OTP_SECRET` to random values of at
least 32 characters. Production startup rejects missing values. Development and
tests can use process-local fallbacks, but stable local values are recommended
when multiple workers or restarts are involved.

Development can use Gmail SMTP by setting `AUTH_EMAIL_PROVIDER=smtp`,
`SMTP_HOST=smtp.gmail.com`, port `587`, the Gmail address, a Google App Password,
and `SMTP_STARTTLS=true`. The normal Gmail password must never be used. Production
should move to a transactional sender without changing the authentication flow.

`AUTH_OTP_TEST_CODE` is accepted only when `APP_ENV=test` for isolated,
deterministic acceptance services. It is rejected outside that environment.

The access and refresh lifetimes can be configured with
`AUTH_ACCESS_TOKEN_TTL_SECONDS` and `AUTH_REFRESH_TOKEN_TTL_DAYS`.

Set `OAUTH_WEB_BASE_URL` to the public dashboard origin. Register these exact
callback URLs with each provider:

- `https://<dashboard>/api/auth/oauth/google/callback`
- `https://<dashboard>/api/auth/oauth/microsoft/callback`
- `https://<dashboard>/api/auth/oauth/github/callback`

When the platform admin uses a separate hostname, set `OAUTH_ADMIN_WEB_BASE_URL`
and register the same callback paths on that hostname.

Set the matching `OAUTH_*_CLIENT_ID` and `OAUTH_*_CLIENT_SECRET` values only in
the server environment or secret manager. A provider stays disabled until both
values exist. The Microsoft tenant setting defaults to `common`; use a tenant ID
when the deployment is restricted to one Entra tenant.
