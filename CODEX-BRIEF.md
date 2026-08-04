# Codex Brief 001 — Secure the work, then prove it actually works

> **You are the implementing agent.** Read this file completely before running any command.
> This brief was produced by a full repository review. It supersedes "pick the next unchecked
> task in `TASKS.md`" for this session only.

## Required reading order

1. This file, completely.
2. `AGENTS.md` — the completion contract and engineering rules still apply in full.
3. `CONTEXT.md` §5 (persistent user instructions) and the `HANDOFF STATE` block.
4. `PLAN.md` §5 (isolation rules), §7 (retrieval), §12 (testing and observability).

Do **not** start `T-051` or any other unchecked feature task. Two defects block all further
feature work, and both are described below.

---

## What the review found

The code quality is good. Tenant predicates, Argon2id hashing, refresh-token rotation with
family revocation, SSRF guards in the crawler, the append-only usage trigger, and the
row-level-security policies are all soundly written.

Two problems make that quality unverifiable and unsafe to build on.

### Problem 1 — roughly twenty tasks of work exist only in the working tree (P0)

`git log` stops at `[T-024] add append-only usage events`. Everything after it is uncommitted:

- untracked: `apps/api/app/domains/knowledge/`, `apps/api/app/domains/chat/`,
  `apps/api/app/providers/` (storage, embeddings, llm, router, factory, types,
  openai_compatible), `apps/api/app/workers/`, `apps/api/app/evals/`,
  `apps/api/app/api/knowledge.py`, `apps/api/app/api/widget.py`,
  migrations `0006_knowledge_ingestion.py`, `0007_document_chunks.py`, `0008_conversations.py`,
  eleven test modules, nine `docs/*.md` files, and the entire `apps/web/` dashboard
  (`app/login/`, `app/register/`, `app/dashboard/`, `app/api/`, `components/`, `lib/`).
- modified: `.env.example`, `CONTEXT.md`, `README.md`, `TASKS.md`, `apps/api/alembic/env.py`,
  `apps/api/app/core/config.py`, `apps/api/app/main.py`, `apps/api/pyproject.toml`,
  `apps/api/uv.lock`, `apps/api/tests/test_alembic.py`, `package.json`, `package-lock.json`,
  `packages/api-client/src/index.ts`, `docs/README.md`, `docs/tenancy.md`, and several
  `apps/web/` files.

`TASKS.md` marks `T-030` through `T-050` as `[x]`. Git contains none of it. A single
`git clean -fd` or a mistaken checkout destroys all of it, and no other agent can review,
resume, or roll back work that was never recorded.

This also breaks `AGENTS.md`: commits must carry task IDs, and the handoff must state
uncommitted work truthfully. The current `HANDOFF STATE` claims `T-020` was the last completed
task, which is now three commits and roughly twenty tasks out of date.

### Problem 2 — the database defense layer has never executed once (P0)

Every test module creates its engine with `sqlite+aiosqlite:///:memory:`. Confirm it yourself:

```bash
grep -rn "create_async_engine" apps/api/tests/ apps/api/app/evals/
```

`app/core/tenancy.py` returns early whenever the dialect is not PostgreSQL:

```python
# set_database_tenant / set_database_user / clear_database_tenant
bind = session.get_bind()
if bind.dialect.name != "postgresql":
    return
```

On SQLite these three functions are no-ops. The consequences:

| Written and shipped | Actually executed by the suite |
|---|---|
| RLS policies in migrations `0002`–`0008` | Never. Not once. |
| The `usage_events` append-only PostgreSQL trigger | Never (only the ORM-level event listener runs) |
| The pgvector branch at `app/domains/knowledge/retrieval.py:172` | Never — SQLite always takes the fallback branch |
| Every migration, upgrade and downgrade | Never against a real PostgreSQL server |
| The agent evaluation suite (`app/evals/agent_quality.py:277`) | Runs on SQLite, so it grades a code path that never serves a user |

So the tests named "cross-tenant isolation" verify only the Python `WHERE tenant_id = :id`
predicate. `PLAN.md` §5 explicitly calls RLS "defense in depth, not a substitute for
application checks" — but defense in depth that has never run is not defense at all, and
`PLAN.md` §12 requires "mandatory isolation tests" for every tenant-owned domain.

`.github/workflows/ci.yml` sets `DATABASE_URL` and `REDIS_URL` pointing at `127.0.0.1`, but
declares **no service containers**. Nothing is listening on those ports in CI. The readiness
test passes because it accepts `503` as a valid outcome.

**Also, a trap you must avoid in step 2 below:** the `pgvector/pgvector` image creates the
`POSTGRES_USER` role as a **superuser**, and PostgreSQL superusers bypass row-level security
even when the table is set to `FORCE ROW LEVEL SECURITY`. If you write the RLS tests while
connected as that role, every test will pass while proving nothing. You must connect as a
dedicated non-superuser role.

---

## Scope of this brief

**In scope**

1. Commit the existing work in reviewable, task-ID-labelled commits.
2. Give CI real PostgreSQL and Redis service containers.
3. Add PostgreSQL integration tests that execute the RLS policies, the append-only trigger,
   the pgvector retrieval path, and the migration chain.
4. Correct `TASKS.md` and the `CONTEXT.md` `HANDOFF STATE` so they match reality.

**Out of scope — do not do these now**

- Any new product feature, including `T-051` and later.
- Rewriting, refactoring, or "improving" the existing domain code. If an integration test
  fails, fix the specific defect it exposes and nothing else.
- Billing, admin UI, human handoff, external integrations, voice, auto-learning.
- Changing the SQLite unit tests. They are fast and useful; they are simply not sufficient.
  Add PostgreSQL tests **alongside** them.

---

## Step 1 — commit the existing work (do this first, before anything else)

Nothing else in this brief matters if the tree is lost.

1. Add ignore rules for local artifacts, then verify nothing sensitive is staged:

   ```bash
   # Append to .gitignore
   .playwright-cli/
   output/
   ```

   Confirm `.env`, `.venv`, `__pycache__`, `*.pyc`, `.data/`, and `node_modules/` are already
   ignored. `git.png` (the Git setup screenshot) must stay out of the repository —
   `AGENTS.md` forbids committing it.

2. Run `git status --short` and read every line. Verify no `.env`, credential, API key, token,
   or `.pyc` file is about to be committed.

3. Commit in task-sized groups, in dependency order, each with its real task ID. Suggested
   grouping — adjust if the actual file boundaries differ:

   | Commit message | Contents |
   |---|---|
   | `[T-030] add storage and ingestion job abstractions` | `providers/storage.py`, `workers/queue.py`, `tests/test_storage.py`, `arq` dependency, storage settings |
   | `[T-031..T-035] add knowledge sources and ingestion pipeline` | `domains/knowledge/`, `api/knowledge.py`, `workers/ingestion.py`, `workers/source_ingestion.py`, migrations `0006`/`0007`, related tests and docs |
   | `[T-036] implement tenant-scoped hybrid retrieval` | `domains/knowledge/retrieval.py`, `tests/test_retrieval.py` |
   | `[T-040] add provider-neutral llm and embedding adapters` | `providers/llm.py`, `embeddings.py`, `types.py`, `factory.py`, `openai_compatible.py`, `tests/test_providers.py`, `docs/providers.md` |
   | `[T-041] add model tiering and failover router` | `providers/router.py`, `tests/test_model_router.py` |
   | `[T-042] implement conversations, messages, and compaction` | `domains/chat/` conversation layer, migration `0008`, `tests/test_conversations.py`, `docs/conversations.md` |
   | `[T-043] implement grounded rag answer orchestration` | orchestrator, `tests/test_grounded_orchestrator.py`, `docs/agent-orchestration.md` |
   | `[T-044] add streaming chat api and widget sessions` | `api/widget.py`, `tests/test_widget_chat.py`, `docs/widget-chat-api.md` |
   | `[T-045] add agent quality and safety evaluation set` | `app/evals/`, `apps/api/evals/`, `run_agent_eval.py`, `tests/test_agent_evaluation.py`, `docs/agent-evaluations.md` |
   | `[T-050] build dashboard shell and auth flow` | `apps/web/` additions, `packages/api-client/src/index.ts`, `docs/dashboard-auth.md` |

   If a clean split proves impractical because files are entangled, do **not** stall. Make one
   honest commit — `[T-030..T-050] add knowledge, agent, and dashboard implementation` — with a
   body listing each task ID it covers. An accurate large commit is far better than lost work.

4. Do **not** push. `AGENTS.md` treats pushing as an external action requiring the user's
   explicit authorization for the active request. Committing locally is what protects the work.

5. Before moving on, confirm: `git status --short` shows only intentionally-ignored files, and
   `npm run check` still passes.

---

## Step 2 — give CI real PostgreSQL and Redis

Edit `.github/workflows/ci.yml`. Add a `services:` block to the `lint-and-test` job, keeping
the existing `env:` block:

```yaml
jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    env:
      APP_ENV: test
      DATABASE_URL: postgresql+asyncpg://support_agent:ci_only@127.0.0.1:5432/support_agent_test
      REDIS_URL: redis://127.0.0.1:6379/15
      AUTH_JWT_SECRET: ci-only-auth-secret-not-used-outside-tests
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_DB: support_agent_test
          POSTGRES_USER: support_agent
          POSTGRES_PASSWORD: ci_only
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U support_agent -d support_agent_test"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 12
      redis:
        image: redis:7.4-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 5s
          --health-timeout 3s
          --health-retries 12
```

Then add a migration step **before** `npm run check`:

```yaml
      - name: Apply database migrations
        run: npm run db:upgrade
```

This alone proves migrations `0001`–`0008` apply cleanly against a real pgvector-enabled
PostgreSQL — something that has never been verified.

---

## Step 3 — create the non-superuser application role

This is the step that makes the RLS tests meaningful. Superusers bypass RLS.

Add a new migration, `0009_app_runtime_role.py`, or a dedicated test-bootstrap SQL fixture —
your choice, but state which you chose in the handoff. It must:

1. Create a role that is **not** a superuser and does **not** have `BYPASSRLS`, for example
   `support_agent_app`.
2. Grant it `CONNECT` on the database, `USAGE` on the `public` schema, and
   `SELECT, INSERT, UPDATE, DELETE` on the tenant-owned tables it must reach.
3. Grant no ownership of those tables, so `FORCE ROW LEVEL SECURITY` is not the only thing
   standing between the role and the data.

Then add a `TEST_DATABASE_URL` environment variable that connects **as that role**, and use it
for the RLS tests specifically. Document it in `.env.example` with a comment explaining
precisely why a second, weaker connection string exists — otherwise a future agent will
"simplify" it away and silently disable every RLS test.

Add an assertion in the test fixture itself:

```python
row = await session.execute(text(
    "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
))
is_super, bypasses_rls = row.one()
assert not is_super, "RLS tests are meaningless when connected as a superuser"
assert not bypasses_rls, "RLS tests are meaningless with BYPASSRLS"
```

Without this assertion the suite can silently degrade to proving nothing. Include it.

---

## Step 4 — add the PostgreSQL integration test fixtures

Create `apps/api/tests/conftest.py` (or extend it if one now exists) with:

1. A session-scoped `postgres_engine` fixture reading `TEST_DATABASE_URL`, falling back to
   `DATABASE_URL`.
2. `pytest.skip(...)` with a clear message when the server is unreachable, so a developer
   without Docker running still gets a usable local suite. CI must **not** skip — assert that
   when `CI=true` is set, an unreachable database is a hard failure, never a skip. A silently
   skipped security test is worse than no test.
3. A `pg_session` fixture yielding an `AsyncSession` bound to that engine, rolling back after
   each test.
4. A `pytest` marker, `@pytest.mark.integration`, registered in `pyproject.toml` under
   `[tool.pytest.ini_options] markers`.

---

## Step 5 — write the tests that prove the database actually defends itself

Create `apps/api/tests/test_rls_isolation.py`. For **every** tenant-owned table —
`tenant_memberships`, `refresh_tokens`, `bots`, `bot_keys`, `usage_events`, and every table
introduced by migrations `0006`, `0007`, and `0008` — assert all four of the following. Use
raw SQL through the session, not the repositories: the repositories add their own `tenant_id`
predicate, which would mask a missing or broken policy.

1. **Cross-tenant read is empty.** Insert a row for tenant B. Set
   `SELECT set_config('app.tenant_id', '<tenant-A-uuid>', true)`. A raw
   `SELECT * FROM <table>` must return zero rows.
2. **Cross-tenant write fails.** Under tenant A's GUC, an `UPDATE` or `DELETE` targeting
   tenant B's row must affect zero rows, and an `INSERT` carrying tenant B's `tenant_id` must
   raise. This is the `WITH CHECK` half of the policy, and nothing currently tests it.
3. **No tenant context means no data.** With the GUC unset or empty, every query must return
   zero rows and every insert must fail. Confirm the policy genuinely fails closed.
4. **The append-only guarantee holds at the database level.** A raw
   `UPDATE usage_events SET ...` and a raw `DELETE FROM usage_events` must each raise the
   `usage_events is append-only` exception from the trigger — proving the guarantee survives
   even when the ORM listener is bypassed.

Then add `apps/api/tests/test_retrieval_postgres.py`:

- Run the same retrieval scenarios as `test_retrieval.py`, but against PostgreSQL so the
  `dialect.name == "postgresql"` branch at `retrieval.py:172` actually executes.
- Assert the pgvector similarity search returns correctly ordered results.
- Assert that a query issued under tenant A never returns tenant B's chunks — this is the
  single most important isolation test in the entire system, because retrieval is what feeds
  the model, and a leak here sends one company's private documents to another company's
  customer.

Then extend `apps/api/tests/test_alembic.py`:

- `alembic upgrade head` → `alembic downgrade base` → `alembic upgrade head` against real
  PostgreSQL, asserting each step succeeds. Several downgrade paths drop policies, triggers,
  and functions and have never been executed.
- Assert model/migration parity: after `upgrade head`, an autogenerate pass must produce an
  empty diff. Drift between `app/domains/*/models.py` and the migration files is currently
  invisible.

---

## Step 6 — point the evaluation suite at PostgreSQL

`app/evals/agent_quality.py:277` builds a SQLite engine. The evaluation suite exists to answer
"is the agent good enough to ship", and it currently answers that question about a code path
that never serves a real request — retrieval in particular behaves differently.

Make the evaluation harness accept a database URL, defaulting to `TEST_DATABASE_URL` when
present. Keep SQLite available as an explicit opt-in for fast local iteration, and record in
`docs/agent-evaluations.md` that only a PostgreSQL run counts as a release signal.

---

## Step 7 — make the documentation truthful

1. **`TASKS.md`** — `T-013` has already been added for you in Phase 1A, immediately after
   `T-012`. Check its box only once every acceptance criterion below is genuinely met. Leave
   `T-030`–`T-050` checked; the implementation genuinely exists, and `T-013` is what verifies
   the isolation guarantees they claim.

2. **`CONTEXT.md`** — replace the stale `HANDOFF STATE` block. It currently claims `T-020` was
   the last completed task. Record the true last commit, the true set of completed tasks, the
   fact that this brief drove the session, and any work still uncommitted when you stop.

3. **`docs/tenancy.md`** — add a short section stating that tenant isolation has two layers
   (the application predicate and PostgreSQL RLS), that RLS is only exercised by the
   PostgreSQL integration tests, and that a non-superuser role is mandatory for those tests to
   mean anything. Write it so a future agent cannot "simplify" the second connection string
   away without realizing what breaks.

---

## Acceptance criteria

Do not mark `T-013` complete until every one of these holds:

- [ ] `git status --short` shows only intentionally-ignored files.
- [ ] `git log --oneline` shows the implementation work committed with real task IDs.
- [ ] `.gitignore` covers `.playwright-cli/` and `output/`; no `.env`, secret, or `git.png` is tracked.
- [ ] CI declares PostgreSQL (pgvector) and Redis services, and runs migrations before tests.
- [ ] A non-superuser role exists, and the fixture asserts `rolsuper` and `rolbypassrls` are both false.
- [ ] Cross-tenant `SELECT`, `UPDATE`, `DELETE`, and `INSERT` are each proven to fail for every tenant-owned table.
- [ ] Absent tenant context is proven to return no rows and reject writes.
- [ ] Raw `UPDATE` and `DELETE` on `usage_events` are proven to raise at the database level.
- [ ] The pgvector retrieval branch executes under test and is proven not to leak across tenants.
- [ ] `upgrade head` → `downgrade base` → `upgrade head` succeeds against real PostgreSQL.
- [ ] Autogenerate produces an empty diff against the models.
- [ ] `npm run check` passes locally and in CI.
- [ ] `TASKS.md`, `CONTEXT.md`, and `docs/tenancy.md` are updated.

**Report honestly.** If an integration test exposes a real defect in existing code, that is a
success, not a failure — it is the entire reason for this work. Fix that specific defect, state
plainly what was broken and what you changed, and keep going. If something cannot be completed,
leave the task unchecked and write the exact next step in the handoff. Never check a box to make
the list look finished.

---

## Appendix — smaller findings, for separate follow-up tasks

Do **not** fix these in this session. Record them so they are not lost.

1. **Per-process JWT secret.** `app/core/config.py` generates
   `_ephemeral_local_auth_secret` at import time. Running `uvicorn --workers 4` gives each
   worker a different secret, so a token minted by one worker is rejected by another — an
   intermittent, confusing authentication failure. Either derive the development secret
   deterministically, or refuse to start with more than one worker when `AUTH_JWT_SECRET` is
   unset.

2. **Import-time Redis client.** `app/api/health.py:16` calls `Redis.from_url(...)` at module
   import, and `app/main.py` reaches into `health.redis_client` to close it during shutdown.
   Move the client into the lifespan and onto `app.state` so importing a router does not create
   a connection object and `main.py` does not depend on a router's global.

3. **Silent dependency downgrade.** `apps/api/pyproject.toml` moved `redis` from `>=8.1.0` to
   `>=5.2,<6.0` to satisfy `arq`. That is a legitimate constraint, but it must be an explicit,
   commented decision rather than an unexplained narrowing, and `PLAN.md` §2 commits only to
   "start with ARQ behind an application interface" — verify the interface boundary actually
   holds so the queue can be replaced without a domain rewrite.

4. **Generated API client is still a stub.** `packages/api-client/src/index.ts` exports only
   `API_VERSION`. `PLAN.md` §2 requires OpenAPI-generated TypeScript types so the Python and
   TypeScript contracts stay synchronized. Until that exists, dashboard and widget types can
   drift from the API without any check failing.
