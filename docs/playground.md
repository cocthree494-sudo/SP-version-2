# Tenant playground and usage summary

T-052 adds a private dashboard playground at `/dashboard/playground`. An
authenticated tenant member chooses one of the organization's bots, starts a
`playground` conversation, and receives the grounded answer as server-sent
events. Reset creates a new conversation while the old thread remains governed
by the normal conversation-retention policy.

The interface exposes retrieval/stream state, safe fallback state, and citations
returned by the channel-neutral answer orchestrator. It never uses a public
widget key. Both session creation and every turn use the tenant-bound dashboard
access token, repository predicates, and PostgreSQL RLS. A conversation from a
different tenant or channel is rejected.

The side panel reads `GET /v1/usage/summary`, filtered to the selected bot. It
shows total tokens, event count, average latency, estimated configured cost, and
provider/model/operation breakdowns. This is an informational summary, not a
billing ledger or quota mechanism.

The Next.js BFF streams SSE without exposing access or refresh tokens to browser
JavaScript. Changing bots or resetting a thread cancels any current browser
stream. Provider routing follows the selected tenant's explicit platform/BYOK
policy, and tenant-only routing fails safely if it has no verified active target.
