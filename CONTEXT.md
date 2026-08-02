# Session Context — Universal Support Agent

> Read this first. This is the compact handoff document for Claude, Codex, or another coding agent. Detailed architecture is in [PLAN.md](PLAN.md); executable order is in [TASKS.md](TASKS.md).

**Last updated:** 2026-08-02, Codex handoff session
**Status:** planning and repository handoff complete; application code has not started.

## 1. Project

Build a multi-tenant SaaS customer-support AI agent. A company signs up, adds its own knowledge base, gets a bot, and uses the same channel-agnostic core on its website and later WhatsApp, Telegram, Messenger, and email.

User priorities:

- world-class answer quality;
- very low model/token cost;
- multilingual replies;
- provider/model failover so one API outage does not take down the bot;
- memory, database, and RAG;
- a visually dynamic, **super-fast** web experience;
- documentation that lets Claude/Codex continue without repeating discovery.

## 2. Decisions

| ID | Decision | Why / source |
|---|---|---|
| D1 | Multi-tenant from day one | Final product is SaaS; tenant isolation cannot be bolted on safely later |
| D2 | Channel-agnostic core; web widget first | All major channels are desired, but each channel should be a thin adapter |
| D3 | Python + FastAPI backend | User chose the recommended backend direction |
| D4 | Human handoff is deferred | User wants the basic working product first |
| D5 | Knowledge sources: website crawl, PDF/DOCX/TXT/MD upload, manual Q&A | User wanted all proposed sources except burdensome external integrations |
| D6 | MVP business layer: auth, organization, roles, usage/token tracking; no Stripe | Recommended minimal SaaS foundation accepted |
| D7 | Work in small, working MVP slices | User accepted the fast-MVP direction and will switch between Claude/Codex when limits are reached |
| D8 | Frontend default: Next.js dashboard + lightweight Preact/Vite widget | Best current fit for dynamic dashboard plus a small customer-site bundle; can change before scaffold if user requests |
| D9 | Docker/env-configured, hosting-agnostic code | Hosting and budget are not decided |
| D10 | Provider/model IDs stay configurable | Enables tiering/failover and avoids vendor logic in the domain layer |

## 3. Deferred scope

Do not build these now unless the user explicitly changes priority:

- Stripe subscription, plan tiers, quota enforcement, invoices;
- full account-management and platform-admin UIs;
- human handoff/live-agent inbox, assignment, takeover;
- Notion, Zendesk, Shopify, Intercom, or similar integrations;
- voice support;
- automatic KB learning from resolved tickets;
- consent-aware long-term customer profile memory.

The Phase 1 schema and interfaces should leave clean extension points for them without implementing them prematurely.

## 4. Technical direction

- FastAPI, Next.js, Preact/Vite widget.
- PostgreSQL + pgvector, Redis, SQLAlchemy/Alembic.
- Redis-backed background ingestion worker.
- Local storage adapter for development and S3-compatible adapter later.
- Hybrid vector + lexical retrieval, citations, grounded fallback.
- Low-cost model first, stronger model promotion for complex/failed cases.
- Provider adapter + normalized errors + retry/circuit-breaker interface.
- Conversation recent-window plus server-side rolling summary.
- Streaming chat over SSE.
- All tenant-owned data, jobs, caches, storage paths, and retrieval are tenant-scoped.

## 5. User instructions that must persist

1. Record important questions, answers, decisions, and completed steps so another AI can continue cheaply.
2. Avoid spending time/tokens building the large SaaS/business layer before the working bot MVP.
3. Keep tasks small enough for one focused coding session.
4. Use task IDs in commit messages, for example: `[T-021] add tenant schema`.
5. The user intended to share more features but could not remember them. Keep [FEATURES.md](FEATURES.md) as the inbox.

## 6. Session log

### Session 1

- User described the universal support bot, cost, quality, multilingual, failover, memory, DB, and RAG goals.
- Claude proposed the initial architecture and created `CONTEXT.md` and `PLAN.md`.

### Session 2 — Claude

- Asked scope, channel, stack, handoff, hosting, KB sources, SaaS-layer scope, and pace questions.
- Recorded D1–D7 and open hosting/provider questions.
- Recommended a working MVP first and Next.js if the user had no frontend preference.
- Proposed the cross-agent system: `AGENTS.md`, `CLAUDE.md`, `TASKS.md`, a handoff block, and task-ID commits.
- Work stopped because Claude usage reached its limit before those files and Git setup were completed.

### Session 3 — Codex

- Read the pasted Claude terminal conversation and existing docs.
- Inspected `git.png`; identified GitHub repository `cocthree494-sudo/support-agent`.
- Expanded the technical plan and created the task/handoff system.
- Created the extra-feature inbox requested by the user.
- Selected D8 as a reversible implementation default.

## 7. Open items

| ID | Item | Handling now |
|---|---|---|
| O1 | Hosting and budget | Use Docker and environment configuration; decide before production deployment |
| O2 | Model/embedding API keys and exact IDs | Use configuration and deterministic mocks if unavailable |
| O3 | Extra feature ideas | Wait for user; capture in `FEATURES.md` |
| O4 | Visual brand/design direction | Do not block backend/foundation work |

## HANDOFF STATE

**Last completed:** T-001 — planning, handoff documents, and Git repository setup  
**Next task:** T-010 — scaffold the monorepo and local development stack  
**Blocked on:** none; provider credentials are not required for scaffold work  
**Uncommitted work:** none expected after the handoff commit  
**Verification:** documentation cross-links checked; Git status/remote/push must be confirmed at session end  
**Gotchas:** the GitHub screenshot showed an SSH URL, but this PC had not trusted GitHub's SSH host key; HTTPS is the safe initial remote. Do not commit `git.png` or `.claude/settings.local.json`.
