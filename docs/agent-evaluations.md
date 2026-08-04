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
responses and an in-memory database, so it needs no provider key, PostgreSQL, or
Redis and is suitable for CI regression checks.

This set is a fast policy/behavior gate, not a substitute for later live-model
quality measurement, adversarial red-teaming, or production PostgreSQL RLS
integration tests.

