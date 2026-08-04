# Agent quality and safety evaluations

T-045 adds a credential-free evaluation set for grounding, uncertainty
fallback, Bengali same-language behavior, citation enforcement, knowledge-base
prompt injection, and cross-tenant conversation rejection.

Run the concise report from the repository root:

```powershell
npm.cmd run eval:agent
```

Use `npm.cmd run eval:agent -- --json` for a stable machine-readable report. The
command exits non-zero when any case fails. Cases live in
`apps/api/evals/agent_quality_cases.json`; the runner uses deterministic model
responses. In CI and release review it defaults to the migrated PostgreSQL URL
in `TEST_DATABASE_URL`, so tenant/RLS behavior is part of the signal. For fast
local iteration without infrastructure, explicitly opt into SQLite:

```powershell
uv run --project apps/api python apps/api/run_agent_eval.py --sqlite
```

Only a PostgreSQL run counts as a release-quality evaluation signal.

This set is a fast policy/behavior gate, not a substitute for later live-model
quality measurement, adversarial red-teaming, or production PostgreSQL RLS
integration tests.
