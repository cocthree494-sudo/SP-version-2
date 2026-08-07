# Relay team showcase — presenter guide

Recommended runtime: **35–45 minutes**, including a 7–10 minute live demo and Q&A. The deck is intentionally comprehensive; for a 20-minute slot, present slides 1–8, 10, 13–17, 21–26, then close on 27.

## Story arc and timing

| Slides | Theme | Time |
| --- | --- | ---: |
| 1–6 | Problem, users, journey, product scope | 7 min |
| 7–10 | Architecture, stack, repository, isolation | 8 min |
| 11–17 | Security and AI/data pipeline | 10 min |
| 18–20 | Experience, data model, API | 5 min |
| 21–24 | Evidence, performance, operations, decisions | 7 min |
| 25 | Live demo | 7–10 min |
| 26–27 | Roadmap and close | 3 min |

## Slide-by-slide Bengali cues

1. **Relay** — “আজকে শুধু UI দেখাব না; problem থেকে production-ready MVP পর্যন্ত পুরো engineering story দেখাব।”
2. **Executive summary** — Signup → knowledge → grounded answer → widget—এই একটিমাত্র loop-ই product-এর core value।
3. **Why we built it** — Support knowledge ছড়িয়ে থাকে, answer inconsistent হয়, আর generic AI trust তৈরি করতে পারে না। Relay-এর লক্ষ্য trusted, cited, tenant-safe answer।
4. **Personas** — Owner control করে billing/config; admin knowledge ও bot চালায়; agent outcome দেখে; visitor শুধু fast answer চায়।
5. **Tenant journey** — সাত ধাপের happy path বলুন; প্রতিটি ধাপ একই tenant boundary-এর মধ্যে থাকে।
6. **Feature map** — এটি MVP হলেও auth, ingestion, retrieval, routing, widget, analytics ও ops একসঙ্গে complete vertical slice।
7. **Architecture** — Channel adapter বদলালেও core agent বদলায় না। API fast path এবং worker slow path আলাদা।
8. **Tech stack** — FastAPI ও Next.js productivity, PostgreSQL/pgvector operational simplicity, Redis/ARQ async work, SSE low-complexity streaming দিয়েছে।
9. **Repository** — Monorepo shared contracts ও one-command delivery সহজ করেছে; migrations, tests, widget ও infra পাশাপাশি versioned।
10. **Tenant isolation** — Tenant ID শুধু UI filter না; query, cache, queue, vector lookup এবং test—প্রতিটি layer-এর invariant।
11. **Auth and roles** — Secure cookie session, CSRF protection এবং owner/admin/agent permissions-এর layered enforcement বোঝান।
12. **Ingestion** — Upload/URL API-কে block করে না; job worker parse, chunk, embed করে এবং status observable রাখে।
13. **Hybrid retrieval** — Vector semantic meaning ধরে, keyword exact term ধরে; merge/rerank-এর পর tenant-scoped evidence আসে।
14. **Grounded agent** — Evidence ছাড়া confident answer নয়। Prompt, citation validation এবং safe fallback hallucination risk কমায়।
15. **Model router** — Capability/config ভিত্তিক provider নির্বাচন; retriable failure-এ bounded failover; provider core logic-এর বাইরে।
16. **BYOK** — Key encrypted at rest, masked in UI/API, scoped at runtime; logs বা response-এ raw secret যায় না।
17. **Streaming** — SSE simple one-way token delivery; reconnect/final event semantics UI-কে stable রাখে।
18. **UX** — Dashboard setup-এর জন্য, playground verification-এর জন্য, widget end-customer outcome-এর জন্য। Actual landing screenshot দেখান।
19. **Data model** — Organization root থেকে bot/source/conversation lineage; FK ও tenant scoping মিলিয়ে traceability।
20. **API surface** — 34 routes random collection নয়; lifecycle অনুযায়ী grouped contract।
21. **Acceptance** — 86 integration tests, 6/6 agent eval, 3/3 browser flow—“works on my machine” নয়, repeatable evidence।
22. **Performance** — p95 values পড়ুন; বিশেষ করে first-ready 10.58 ms এবং source-ready 543.22 ms। Widget মোট 10,539 B gzip।
23. **Operations** — Production Compose, migrations, health checks, backups ও immutable-image recovery operational baseline তৈরি করেছে।
24. **Decisions** — প্রতিটি decision-এর benefit ও accepted trade-off দুটোই বলুন; deferred item-কে delivered বলে দাবি করবেন না।
25. **Live demo** — নিচের scripted flow অনুসরণ করুন; demo data আগে থেকে প্রস্তুত রাখুন।
26. **Roadmap** — Phase 1 accepted; next focus connectors, richer analytics, enterprise controls, then channel expansion।
27. **Close** — “Relay-এর differentiation শুধু AI answer নয়—grounding, isolation, provider choice এবং operational proof একসঙ্গে।”

## Live demo checklist

1. Fresh tenant signup and dashboard landing.
2. Create a bot and save its identity/instructions.
3. Add a small text or URL knowledge source; wait until status is `ready`.
4. Ask one answerable question in Playground and open its citations.
5. Ask one out-of-scope question to show the safe fallback.
6. Open model settings and explain BYOK masking without exposing a real key.
7. Copy the embed snippet and show the widget conversation.
8. End on conversation visibility and the operations/health proof.

## Q&A anchors

- **Why not WebSocket?** Server-to-client token streaming is the MVP need; SSE is simpler to proxy and operate.
- **Why pgvector instead of a separate vector database?** One transactional tenant-aware datastore reduces operational surface at this scale.
- **How do we prevent cross-tenant retrieval?** Tenant scope is applied before retrieval and covered by negative integration tests.
- **What if a model provider fails?** The provider-neutral router applies bounded failover for retriable failures.
- **What is deliberately not finished?** Billing enforcement, broader connectors/channels, advanced analytics, SSO/SCIM, audit export, and autoscaling remain roadmap items.

## Before presenting

- Use the PPTX for presentation mode or the PDF for guaranteed visual fidelity.
- Run the demo once against the exact environment and keep the PDF open as a fallback.
- Never display `.env`, provider keys, cookies, or production tenant data.
- When describing roadmap items, clearly separate them from accepted Phase 1 behavior.
