# Anonymous widget chat API

T-044 exposes two public, origin-checked endpoints:

- `POST /v1/widget/{publishable_key}/sessions` creates a tenant/bot-bound
  conversation and returns a short-lived bearer token.
- `POST /v1/widget/{publishable_key}/messages` accepts that token and streams
  the grounded response as `text/event-stream`.

The publishable key is an identifier, not a secret. Every request still requires
an exact allowed `Origin`. Session JWTs have a distinct token type/audience and
bind tenant, bot, key, conversation, origin, and a random token ID. Message
requests re-check the signature, expiry, exact origin, current key revocation,
bot status, and conversation ownership, so revoking a key invalidates existing
sessions immediately.

Browser preflight is handled on the same key-addressed routes. Successful
responses echo only the validated exact origin and include `Vary: Origin`;
wildcard CORS is never used.

SSE events are JSON payloads:

- `ready` — request accepted and conversation identified;
- `text_delta` — append text;
- `replace_text` — replace a completed streamed draft with the safe localized
  fallback when post-stream grounding validation fails;
- `citations` — validated citation metadata;
- `completed` — persisted message IDs and routing/fallback metadata;
- `error` — a safe terminal message without provider or prompt details.

Disconnecting closes the model stream in `finally`; incomplete turns are not
persisted. Fixed-window rate limits use Redis Lua atomically. Keys include the
tenant and bot IDs plus a hash of the client/session identity. Redis failure is
fail-closed for public traffic. Local tests may inject the in-memory equivalent.

