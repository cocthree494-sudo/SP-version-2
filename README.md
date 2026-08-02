# Universal Support Agent

Multi-tenant, multilingual customer-support AI SaaS with tenant knowledge bases, RAG, model cost routing, and provider failover.

The repository foundation is in place. Product implementation continues from the first unchecked task in `TASKS.md`.

## Local development

Prerequisites:

- Node.js 24 or newer
- [`uv`](https://docs.astral.sh/uv/) for Python environments
- Docker Desktop with Docker Compose for PostgreSQL/pgvector and Redis

From a fresh clone, one command creates `.env`, installs JavaScript and Python dependencies, starts the infrastructure, and runs all development servers:

```powershell
npm run dev
```

The first run downloads a managed Python 3.12 interpreter if one is not installed. Review `.env` before using non-local credentials.

| Service | Local URL |
|---|---|
| FastAPI | `http://127.0.0.1:8000` |
| FastAPI OpenAPI | `http://127.0.0.1:8000/docs` |
| Next.js dashboard | `http://127.0.0.1:3000` |
| Widget development page | `http://127.0.0.1:5173` |
| PostgreSQL/pgvector | `127.0.0.1:5432` |
| Redis | `127.0.0.1:6379` |

Useful commands:

```powershell
npm run setup       # install dependencies without starting services
npm run infra:up    # start PostgreSQL and Redis
npm run db:upgrade  # apply pending PostgreSQL migrations
npm run db:current  # show the current Alembic revision
npm run dev:apps    # run API, dashboard, and widget after setup
npm run infra:down  # stop local infrastructure
npm run build       # build JavaScript workspaces
```

The Compose stack uses named volumes, so `infra:down` does not delete local database data.

## Start here

- [CONTEXT.md](CONTEXT.md) — decisions, history, and current handoff
- [TASKS.md](TASKS.md) — execution order and next task
- [PLAN.md](PLAN.md) — detailed product and technical architecture
- [FEATURES.md](FEATURES.md) — unconfirmed feature idea inbox
- [AGENTS.md](AGENTS.md) — rules for Codex/other coding agents
- [CLAUDE.md](CLAUDE.md) — Claude entry point

For a coding agent, the normal instruction is simply: **continue**.
