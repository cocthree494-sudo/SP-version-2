# Provider release readiness (T-074)

The provider surface is released through one fail-closed matrix. A provider is
enabled only when its catalog row, adapter registry entry, credential lifecycle,
model validation, routing policy, redaction, and failure tests all pass.

| Gate | Evidence | Result |
| --- | --- | --- |
| Catalog coverage | Hermes revision and 40 catalog rows | Pass |
| Shared adapters | 21 explicit adapter specs and fixed HTTPS origins | Pass |
| Model setup | Catalog/model validation; custom `/models` discovery | Pass |
| Credential custody | AES-GCM envelope, masked inventory, rotation/revocation | Pass |
| Routing | Low-cost/strong selection, retry, circuit, failover before text | Pass |
| Tenant isolation | Owner/admin gate, tenant predicates, migration/RLS checks | Pass |
| Egress | Custom HTTPS/DNS/IP/redirect/size protections | Pass |
| UI | Searchable catalog, model dropdowns, responsive provider form | Pass |

Operational release rules:

- `platform_only`, `tenant_first_with_platform_fallback`, and `tenant_only` are
  explicit tenant policy choices; no silent fallback is added.
- Provider-visible diagnostics expose provider/model, route reason, attempts,
  latency, and failure category only. Secrets, prompts, and response bodies are
  never included.
- Native OAuth/cloud/local providers remain unavailable until a dedicated
  adapter and terms/token-refresh review are added. The catalog never implies
  support merely because a provider is listed.
- Before a production rollout, run the API provider suites, web typecheck/lint,
  migration checks, and a live health/browser smoke test against the deployment.
