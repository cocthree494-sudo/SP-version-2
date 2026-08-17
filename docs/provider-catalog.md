# Provider catalog

The dashboard provider picker is backed by a versioned, data-driven catalog in
`apps/api/app/domains/provider_access/catalog.py`. It mirrors the provider
coverage shown in the official [Hermes Agent provider documentation](https://hermes-agent.nousresearch.com/docs/integrations/providers).

- Source captured: 2026-08-13
- Upstream `main` revision: `6aaa181f0eb4dd517d9cf163733e7e41a8e126e1`
- Setup methods: API key, OAuth, cloud account, local endpoint, and custom endpoint
- Current runtime: OpenAI and the vetted OpenAI-compatible API-key adapters are
  enabled (OpenRouter, Fireworks, NovitaAI, Vercel AI Gateway, z.ai/GLM,
  Kimi/Moonshot, Arcee, GMI Cloud, MiniMax, xAI, Alibaba DashScope, DeepSeek,
  Hugging Face, Google/Gemini, NVIDIA Build, Ollama Cloud, and StepFun). They share the
  hardened transport, verification, routing, and redaction contract.
- Native API, OAuth, cloud-role, local, and custom entries remain visible as
  “coming soon” until their dedicated adapter and security tests are delivered
  in T-072/T-073.

The catalog is intentionally separate from the `GenerationProvider` database
enum. This lets the product show the complete roadmap without allowing an
unimplemented provider to enter the encrypted credential store.

## Hermes-aligned entries

Nous Portal; OpenAI Codex; GitHub Copilot; GitHub Copilot ACP; Anthropic;
OpenRouter; Fireworks AI; NovitaAI; Vercel AI Gateway; z.ai/GLM;
Kimi/Moonshot; Kimi/Moonshot China; Arcee AI; GMI Cloud; Actual Computer;
MiniMax; MiniMax China; xAI Responses API; xAI Grok OAuth; Qwen/Alibaba
DashScope; Alibaba Coding Plan; Kilo Code; Xiaomi MiMo; Tencent TokenHub;
OpenCode Zen; OpenCode Go; DeepSeek; Hugging Face; Google/Gemini; Google Vertex
AI; OpenAI API; Azure AI Foundry; AWS Bedrock; NVIDIA Build; Ollama Cloud; Qwen
OAuth; MiniMax OAuth; StepFun; LM Studio; Custom Endpoint.
