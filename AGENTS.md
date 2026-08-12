# Coding Agent Instructions

These instructions apply to any coding agent working in this repository.

## Required read order

Before changing code or project files, read completely:

1. `CONTEXT.md`
2. `TASKS.md`
3. `TASK2.md` when Phase 2 work is in scope
4. the relevant sections of `PLAN.md`
5. `FEATURES.md` when scope or product behavior is involved

## Continue protocol

- If the user says only “continue”, select the first unchecked task in the active task file whose dependencies are complete. Phase 2 work uses `TASK2.md`.
- A direct user request overrides the automatic next task. Record any durable scope/architecture change in the docs.
- Keep work to one task at a time unless the user explicitly asks for a batch.
- Do not implement deferred features merely because the schema might support them later.

## Completion contract

Before marking a task complete:

1. implement the full stated output;
2. run checks/tests proportional to the change;
3. inspect the result, including UI behavior when relevant;
4. update the task checkbox;
5. update `CONTEXT.md` session log and `HANDOFF STATE`;
6. record blockers, gotchas, verification, and any uncommitted work truthfully.

Never mark work complete when tests are failing or required work remains. If a task is partially done, keep it unchecked and state the exact next step in the handoff.

## Engineering rules

- Preserve strict tenant isolation in database queries, queues, caches, storage, retrieval, logs, and tests.
- Keep the core agent channel-agnostic and provider-neutral.
- Model/provider IDs and secrets are configuration; never hard-code or commit them.
- Prefer small interfaces and reversible decisions while hosting/providers remain undecided.
- Do not run parsing, crawling, or embedding in API request workers.
- Add or update tests for behavior changes, especially cross-tenant and security-sensitive paths.
- Preserve unrelated user changes in a dirty worktree.

## Git convention

- Use the task ID in commits: `[T-021] add tenant schema`.
- Keep a commit focused on its task and do not claim completed work that is absent.
- Do not commit secrets, `.env`, local AI settings, caches, or the Git setup screenshot.
- Do not rewrite or destroy history without explicit user authorization.
- Pushing is an external action; do it only when the active user request authorizes it.
