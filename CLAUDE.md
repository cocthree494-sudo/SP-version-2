# Claude Project Instructions

Follow [AGENTS.md](AGENTS.md) as the canonical cross-agent workflow.

At the start of every session, read `CONTEXT.md`, `TASKS.md`, and the relevant `PLAN.md` sections. If the user says “continue”, implement the first eligible unchecked task. Before stopping, update the checkbox only if verified, then update the `CONTEXT.md` session log and `HANDOFF STATE` so Codex or another agent can resume without reconstructing the conversation.

Use task IDs in commits. Keep the MVP scope small and do not pull deferred billing, admin, human-handoff, external-integration, voice, or auto-learning work into the current task without an explicit user decision.
