# Phase 2 — Planning and Execution Tasks

This file is the source of truth for Phase 2 planning and implementation order. It supersedes the Phase 2 bucket previously held in `TASKS.md`.

## Working agreement

- The user will share images and ideas. First understand the goal, constraints, user flow, and impact on the existing product; then propose a plan before implementing.
- After the user approves a direction, add focused, sequenced task IDs here. Each task must state dependencies, scope, security/tenant-isolation requirements, and verification expectations.
- Work on one approved task at a time unless the user explicitly requests a batch.
- Do not promote Phase 3 or Phase 4 work, or silently implement a feature merely because the data model could support it.
- Preserve the Phase 1 guarantees: strict tenant isolation, provider-neutral core, secrets never exposed or logged, and background processing for crawling/parsing/embedding.

## Phase 2 product themes

1. Production reliability: real multi-provider redundancy, provider-neutral health/cost policy, and tenant-visible routing audit.
2. Channel expansion: thin adapters around the channel-neutral core, beginning only with channels the user prioritizes.
3. Tenant analytics: retrieval quality, deflection, latency, usage/cost, source freshness, and failure investigation.
4. Durable customer memory: consent-aware design with view, correction, deletion, retention, residency, and channel identity linking designed before implementation.

## Planning inbox

- **Channel direction (now tracked by T-076):** Design the separate `Channels / Integrations` surface for Telegram, WhatsApp Business, Facebook Messenger, and email. Each channel must use its approved connection mode, convert messages to/from the channel-neutral core, and apply channel-specific consent, user identity, rate-limit, and privacy rules. Telegram may use an explicitly user-authorized personal-account connector when the user requires replies from that account; WhatsApp must use the official Business API; Facebook Messenger must use a tenant-owned Page. Do not collect unrelated personal credentials, expose OTPs, or grant access beyond the connected account/page and selected conversations.
- **Voice call agent (now tracked by T-077):** Design and implement a tenant-scoped voice agent through an approved telephony/SIP provider, reusing the channel-neutral agent core. Outbound calling, call recording, and retention remain explicit opt-in capabilities with consent and legal controls.

## Approved tasks

- [x] **T-070 — Add Google, Microsoft, and GitHub social sign-in**  
  Depends on: T-022, T-050  
  Add provider-neutral OAuth/OIDC authentication for Google, Microsoft, and GitHub on both the login and workspace-registration screens. Render compact, official icon-only provider buttons with accessible names, keyboard focus, hover/focus labels, responsive layout, and provider-compliant branding; do not show Apple or magic-link options. Preserve the existing email/password flow.

  Use server-side authorization-code flow with PKCE, high-entropy state, nonce where supported, exact configured callback URLs, and strict provider response/token validation. Keep every client secret and token exchange on the server, configure each provider only through environment variables, request only identity/profile scopes, and reject unverified or invalid identities. Create a provider-identity model keyed by provider, issuer, and subject; never treat an email address alone as a stable identity key. New social users must complete the organization/workspace setup before receiving their normal Relay session. Returning linked users sign in to their selected organization using the existing session/cookie model. A password-account user who selects a matching social email must complete an authenticated account-link flow before that identity is connected, preventing silent linking and account takeover.

  Add the required migration, API/callback contracts, typed web client behavior, provider configuration documentation, and tests for new registration, returning login, organization selection, invalid/replayed state, PKCE/nonce/token validation, callback failure, missing/changed email, cross-tenant isolation, explicit account linking, secret redaction, and disabled/misconfigured providers. Inspect login and registration behavior at desktop and mobile sizes before completion.

- [x] **T-071 — Build the Hermes-aligned provider catalog and setup experience**  
  Depends on: T-046, T-055  
  Create a versioned, provider-neutral generation-provider catalog from the current [Nous Research Hermes Agent inference-provider reference](https://hermes-agent.nousresearch.com/docs/integrations/providers). At task start, capture the exact upstream revision and every listed provider in repository documentation; do not silently omit a provider or present an unsupported provider as usable. Categorize each entry by setup method: API key, OAuth, cloud account/role, local/self-hosted endpoint, or custom endpoint. Record the required configuration fields, supported generation capabilities, model discovery method, tenant eligibility, and implementation status.

  Replace the current single-provider selector with a searchable, grouped dropdown that has official provider marks where licensing permits, clear setup guidance, connection test/status, and an explicit unavailable state. For every catalog provider, users select both the provider and its available low-cost/strong models from dropdowns; they must never type a model ID, label, or provider-specific configuration value. After the user supplies only the API key (or completes the provider's OAuth/cloud connection), fetch the provider's model catalog where supported; otherwise serve a maintained, versioned catalog of valid models. Keep the credential UI write-only and owner/admin-only; preserve the existing routing-policy controls and the email/password authentication work. The catalog must be data-driven so adding or retiring a provider does not require dashboard-specific branching.

  Add catalog contracts, admin APIs, migration/data model changes only where required, masked credential inventory behavior, documentation, and tests for catalog integrity, role/tenant isolation, UI selection, disabled entries, model/config validation, secret redaction, and backwards compatibility for existing OpenAI credentials. Inspect the dropdown and setup flow on desktop and mobile before completion.

- [x] **T-072 — Implement all vetted Hermes-catalog generation adapters**  
  Depends on: T-071  
  Implement and verify every inference provider in the versioned Hermes catalog captured by T-071, using shared transports where protocol-compatible and dedicated adapters where a provider requires a native API, cloud identity, or OAuth flow. Include tenant-owned credential lifecycle, live connection verification, automatic model discovery or a maintained model catalog, normalized streaming/usage/error handling, timeout/retry/circuit integration, and explicit tenant routing/fallback behavior. The completed setup flow must require no typed value beyond the API key for API-key providers; OAuth/cloud providers use their secure connection flow instead. Provider terms, supported account types, and OAuth token-refresh rules must be documented before each OAuth/subscription provider becomes available.

  Each provider must pass the same adapter contract, tenant-isolation, redaction, revocation, routing, and failure tests as the existing provider integration. Do not expose a provider in the enabled dropdown until its adapter and tests pass; retain it as clearly unavailable with a reason rather than implying support. Embedding BYOK remains out of scope.

- [x] **T-073 — Add hardened custom generation-provider setup**  
  Depends on: T-071  
  Add a distinct “Custom provider” path for tenant-owned, OpenAI-compatible generation endpoints. Unlike the predefined catalog, custom setup necessarily requires an HTTPS base URL in addition to a write-only API key or approved no-key mode; derive a safe display label from the verified endpoint and discover models into a dropdown so the user never types a model ID. Show the custom entry in the same catalog and routing controls after verification. Never send custom credentials to the browser after submission or place them in logs, prompts, queues, telemetry, or error bodies.

  Treat every tenant-supplied URL as an untrusted egress destination: reject non-HTTPS, loopback, private, link-local, multicast, metadata, and unsafe redirect targets; resolve and re-check DNS addresses on every connection; block redirect escapes; enforce strict allowlisted request paths, method/header policy, response-size limits, TLS validation, timeouts, and per-tenant rate limits. Add SSRF/DNS-rebinding, cross-tenant, role, redaction, verification, rotation/revocation, routing, and failure tests. This task changes the prior Phase 1 restriction on arbitrary provider base URLs; custom embedding endpoints remain out of scope.

- [ ] **T-074 — Verify multi-provider routing and provider-management release readiness**  
  Depends on: T-072, T-073  
  Run the full provider matrix against configured test accounts/endpoints and deterministic fakes: setup, model selection, health state, normal routing, failover before first streamed text, tenant-only failure, explicit platform fallback, credential rotation/revocation, and custom-provider egress protection. Add provider-visible routing/audit metadata without exposing secrets or message content; measure setup and chat latency/error budgets; update operations, security, and user-facing setup documentation. Perform desktop/mobile browser inspection and production-like integration verification before marking the provider expansion ready.

- [x] **T-075 — Add an account menu with explicit sign-out**  
  Depends on: T-050  
  Replace the current direct sign-out behavior on the dashboard header user control and sidebar user control with one consistent account menu. Clicking the user name/avatar opens, rather than ends, the session. The menu shows the signed-in user’s display name, verified email, current organization/workspace, and role using only the authenticated session data; it provides a clearly labelled “Sign out” action as a separate final menu item. Do not expose tokens, provider secrets, tenant data outside the active organization, or authentication implementation details.

  Implement accessible menu-button behavior: correct expanded state and menu semantics, keyboard operation, focus management, Escape and outside-click dismissal, loading/disabled sign-out state, and responsive placement that does not clip on small screens. Selecting “Sign out” must keep the existing POST-only logout route and cookie clearing, then redirect to login; merely opening, closing, or navigating the account menu must never log the user out. Add component/browser coverage for desktop and mobile behavior, explicit logout, keyboard dismissal, and session-cookie clearing.

- [ ] **T-076 — Add the tenant channel-installation foundation and approved connection modes**  
  Depends on: T-050, T-055  
  Add a dedicated `Channels / Integrations` surface and tenant-scoped installation model. Every installation must bind `tenant_id`, channel type, external account/page identity, connection status, selected conversation scope, consent record, credential reference, expiry/rotation state, and audit metadata. Convert inbound channel events into the existing channel-neutral conversation contract and send the agent response back through the same verified installation; never mix channel identities, conversations, memory, credentials, or queues across tenants.

  Implement the three approved modes without presenting them as interchangeable: (1) Telegram personal-account connection may use an official user-authorized QR/OTP/2FA flow so replies can originate from the connected account, but the platform must never store plaintext OTPs, passwords, or session material in browser storage, logs, prompts, queues, or telemetry. Store any resulting session only in the tenant secret boundary, use an isolated per-tenant connector/worker, support a user-selected session lifetime, pause, disconnect, revoke, and re-authentication, and clearly disclose that QR and OTP create equivalent account-session authority. The Telegram flow must respect Telegram API terms and explicit user consent; it must not silently access unrelated chats. (2) WhatsApp must use the official WhatsApp Business Platform/API, show provider/region-dependent message charges before activation, and must not automate a personal WhatsApp account through an unofficial web session. (3) Facebook Messenger must use a tenant-owned Facebook Page connection and Page API/webhook verification, never a personal profile connection. Email remains an adapter placeholder until its provider and consent requirements are approved.

  Add write-only credential/session handling, webhook signature verification, idempotency, retry/dead-letter behavior, connection health, usage/cost visibility, least-privilege scopes, secret redaction, rate limits, and explicit disconnect cleanup. Add tests for QR/OTP/2FA success and failure, expired/revoked sessions, wrong-tenant access, selected-chat scope, session redaction, Telegram reconnect, WhatsApp API billing/permission failures, Messenger Page-token/webhook validation, duplicate events, channel-specific reply identity, and full tenant isolation. Do not enable a channel in the UI until its connection contract and verification tests pass.

- [ ] **T-077 — Add a tenant-scoped real-time voice call agent**  
  Depends on: T-055, T-071, T-076  
  Add a voice-agent installation surface where a tenant connects an approved telephony/SIP provider and assigns a phone number to one of its logical agents. The connection must be tenant-scoped and store only encrypted provider references, number ownership, call policy, language/voice settings, operating hours, escalation rules, usage limits, and audit metadata. Reuse the channel-neutral conversation contract so voice conversations receive the same tenant-scoped knowledge, provider policy, memory consent, and routing safeguards as web and messaging channels.

  Implement a real-time pipeline of speech-to-text → agent reasoning/provider routing → text-to-speech with streaming audio, interruption/barge-in handling, silence/timeouts, retry/failure states, and a latency budget visible in diagnostics. Support inbound calls first; make outbound calling a separately enabled tenant capability with verified destination, consent/opt-in, do-not-call/opt-out handling, rate limits, caller-ID rules, quiet hours, abuse prevention, and a human approval or campaign policy before dialing. The agent must disclose that it is an AI voice assistant where required, identify the tenant/business, support language and voice selection from an approved catalog, and provide a clear human handoff path to an agent or configured destination. Handoff must preserve the conversation scope and expose an appropriate transcript/summary without leaking secrets or unrelated tenant data.

  Make recording disabled by default. If a tenant enables recording, require an explicit consent announcement, regional recording-policy configuration, retention period, deletion/export controls, access audit, and encrypted storage; transcript and summary retention must be independently configurable. Show per-call and per-minute usage, provider/model cost, latency, failure reason, and limits before activation; do not promise unlimited calling. Add deterministic fake-provider tests and production-like tests for provider connection, inbound call, outbound opt-in, streaming interruption, multilingual text, silence/timeout, transfer/handoff, voicemail, recording consent, retention/deletion, opt-out, duplicate webhook events, provider outage/failover, cost cap, secret redaction, and cross-tenant isolation. Do not expose voice calling in the dashboard until the security, consent, abuse, and end-to-end call verification gates pass.

- [x] **T-078 — Add secure account deletion and email reuse**
  Depends on: T-022, T-050, T-070, T-075
  Add an authenticated account-settings deletion flow with a clear destructive warning, recent-authentication/step-up confirmation, explicit typed confirmation, and a final summary of what will be removed. Revoke every active session and refresh-token family immediately; remove provider identities, linked-login records, personal profile data, and memberships according to the approved retention policy. The deletion path must never log passwords, OAuth tokens, provider secrets, deletion confirmation text, or private customer content.

  Define safe organization handling before deletion: a sole workspace owner must either transfer ownership or explicitly delete the workspace and its tenant data; an owner cannot leave an orphaned workspace; a non-owner may leave the workspace without deleting other members' data. Disconnect/revoke tenant credentials, bot keys, channel sessions, queued jobs, uploads, conversations, and other tenant-owned data through idempotent background cleanup hooks, while retaining only strictly required non-PII audit records. After the user record and login identities are finalized or irreversibly anonymized, the normalized email and provider subject must be available for a new registration with the same Gmail address; deletion retries and concurrent re-registration must be safe and race-free.

  Add owner/member authorization, step-up, idempotency, deletion-status, purge/retry, audit-redaction, cross-tenant isolation, provider-identity removal, same-email re-registration, orphan-workspace prevention, and session-revocation tests. Inspect the account-settings and confirmation flow on desktop and mobile before completion.

- [ ] **T-079 — Add a searchable product documentation center**
  Depends on: T-071, T-075, T-076, T-077, T-078
  Add a public documentation surface and an authenticated in-app Help / Docs page explaining account/login, workspace roles, provider setup and routing, bot/knowledge/widget configuration, channel connections, Telegram QR/OTP session safety, WhatsApp/Facebook approval requirements, voice consent and costs, account deletion, and troubleshooting. Documentation must be versioned from repository source, searchable with keyboard-accessible results, linkable to specific sections, responsive on desktop/mobile, and avoid exposing secrets or internal implementation details. Include a release checklist, provider/channel availability matrix, security and privacy notes, support contact path, and automated link/content smoke tests; update it whenever a completed task changes user-visible behavior.

## Deferred / out of scope

- Phase 3: billing/quotas, platform administration, and human handoff/inbox.
- Phase 4: growth analytics, voice, approved auto-learning, and selected external integrations.
