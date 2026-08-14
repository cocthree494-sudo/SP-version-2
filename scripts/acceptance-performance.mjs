import { mkdir, writeFile } from "node:fs/promises";
import { performance } from "node:perf_hooks";

const baseUrl = (process.env.ACCEPTANCE_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
const sampleCount = Number(process.env.ACCEPTANCE_SAMPLE_COUNT ?? 30);
const password = "Acceptance-performance-password-123!";

if (!Number.isInteger(sampleCount) || sampleCount < 1) {
  throw new Error("ACCEPTANCE_SAMPLE_COUNT must be a positive integer");
}

async function request(path, options = {}) {
  const response = await fetch(`${baseUrl}${path}`, {
    ...options,
    headers: { "content-type": "application/json", ...(options.headers ?? {}) },
  });
  const text = await response.text();
  let body = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  if (!response.ok) {
    throw new Error(`${options.method ?? "GET"} ${path} returned ${response.status}: ${text}`);
  }
  return body;
}

async function measure(label, operation) {
  const samples = [];
  for (let index = 0; index < sampleCount; index += 1) {
    const started = performance.now();
    await operation();
    samples.push(performance.now() - started);
  }
  samples.sort((left, right) => left - right);
  const percentile = (fraction) => samples[Math.min(samples.length - 1, Math.ceil(samples.length * fraction) - 1)];
  return {
    label,
    count: samples.length,
    p50_ms: Math.round(percentile(0.5) * 100) / 100,
    p95_ms: Math.round(percentile(0.95) * 100) / 100,
    p99_ms: Math.round(percentile(0.99) * 100) / 100,
  };
}

async function readSse(response, started) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let text = "";
  let firstEventMs = null;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    text += decoder.decode(value, { stream: true });
    if (firstEventMs === null && text.includes("event: ready")) {
      firstEventMs = performance.now() - started;
    }
  }
  if (!text.includes("event: completed")) {
    throw new Error(`chat stream did not complete: ${text.slice(-500)}`);
  }
  return { totalMs: performance.now() - started, firstEventMs: firstEventMs ?? performance.now() - started };
}

async function main() {
  const live = await request("/health/live");
  const ready = await request("/health/ready");
  const email = `acceptance-${Date.now()}@example.com`;
  const challenge = await request("/v1/auth/register", {
    method: "POST",
    body: JSON.stringify({
      email,
      password,
      display_name: "Acceptance runner",
      organization_name: "Acceptance performance",
    }),
  });
  const otpCode = process.env.ACCEPTANCE_OTP_CODE ?? process.env.AUTH_OTP_TEST_CODE;
  if (!otpCode) {
    throw new Error("Set ACCEPTANCE_OTP_CODE to the isolated test OTP before performance acceptance");
  }
  const tokens = await request("/v1/auth/otp/verify", {
    method: "POST",
    body: JSON.stringify({ challenge_id: challenge.challenge_id, code: otpCode }),
  });
  const authHeaders = { authorization: `Bearer ${tokens.access_token}` };
  const bot = await request("/v1/bots", {
    method: "POST",
    headers: authHeaders,
    body: JSON.stringify({ name: "Performance bot" }),
  });
  const ingestionStarted = performance.now();
  const source = await request(`/v1/bots/${bot.id}/sources/manual`, {
    method: "POST",
    headers: authHeaders,
    body: JSON.stringify({
      name: "Performance answer",
      question: "What is the acceptance answer?",
      answer: "The acceptance answer is deterministic and cited.",
    }),
  });
  const deadline = Date.now() + 120_000;
  let sourceState = source;
  while (sourceState.status !== "ready" && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 500));
    sourceState = await request(`/v1/sources/${source.id}`, { headers: authHeaders });
  }
  if (sourceState.status !== "ready") throw new Error(`source did not become ready: ${sourceState.status}`);
  const ingestionReadyMs = performance.now() - ingestionStarted;

  const endpointResults = [
    await measure("health_live", () => request("/health/live")),
    await measure("health_ready", () => request("/health/ready")),
    await measure("auth_me", () => request("/v1/me", { headers: authHeaders })),
    await measure("bot_list", () => request("/v1/bots", { headers: authHeaders })),
  ];

  const session = await request("/v1/playground/sessions", {
    method: "POST",
    headers: authHeaders,
    body: JSON.stringify({ bot_id: bot.id }),
  });
  const chatSamples = [];
  for (let index = 0; index < sampleCount; index += 1) {
    const started = performance.now();
    const response = await fetch(`${baseUrl}/v1/playground/sessions/${session.conversation_id}/messages`, {
      method: "POST",
      headers: { ...authHeaders, "content-type": "application/json" },
      body: JSON.stringify({ message: "What is the acceptance answer?" }),
    });
    if (!response.ok) throw new Error(`chat returned ${response.status}`);
    const result = await readSse(response, started);
    chatSamples.push({ total: result.totalMs, first: result.firstEventMs });
  }
  const sortedTotal = chatSamples.map((item) => item.total).sort((a, b) => a - b);
  const sortedFirst = chatSamples.map((item) => item.first).sort((a, b) => a - b);
  const percentile = (values, fraction) => values[Math.min(values.length - 1, Math.ceil(values.length * fraction) - 1)];
  const chat = {
    label: "playground_sse_chat",
    count: chatSamples.length,
    first_ready_p95_ms: Math.round(percentile(sortedFirst, 0.95) * 100) / 100,
    total_p50_ms: Math.round(percentile(sortedTotal, 0.5) * 100) / 100,
    total_p95_ms: Math.round(percentile(sortedTotal, 0.95) * 100) / 100,
    total_p99_ms: Math.round(percentile(sortedTotal, 0.99) * 100) / 100,
  };
  const report = {
    generated_at: new Date().toISOString(),
    base_url: baseUrl,
    sample_count: sampleCount,
    provider_mode: process.env.AI_PROVIDER_MODE ?? "deterministic",
    ingestion: {
      label: "manual_source_to_ready",
      total_ms: Math.round(ingestionReadyMs * 100) / 100,
    },
    endpoints: endpointResults,
    chat,
    notes: ["Sequential warm samples; chat combines retrieval, generation, persistence, and SSE delivery."],
  };
  await mkdir("output", { recursive: true });
  await writeFile("output/acceptance-performance.json", `${JSON.stringify(report, null, 2)}\n`);
  const slow = endpointResults.filter((item) => item.p95_ms >= 300);
  if (slow.length > 0) throw new Error(`p95 budget exceeded: ${slow.map((item) => `${item.label}=${item.p95_ms}ms`).join(", ")}`);
  console.log(JSON.stringify(report, null, 2));
  console.log(`live=${live.status} ready=${ready.status} source=${sourceState.status}`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack ?? error.message : error);
  process.exitCode = 1;
});
