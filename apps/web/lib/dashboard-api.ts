import type {
  BotCreateInput,
  BotKeyCreateInput,
  BotKeyResponse,
  BotKeyUpdateInput,
  BotResponse,
  BotUpdateInput,
  ChannelInstallInput,
  ChannelInstallationResponse,
  ChannelStatus,
  VoiceAgentResponse,
  VoiceInstallInput,
  VoiceStatus,
  KnowledgeSourceResponse,
  ManualSourceCreateInput,
  ManualSourceUpdateInput,
  PlaygroundSessionResponse,
  ProviderCatalogEntry,
  ProviderCredentialCreateInput,
  ProviderCredentialResponse,
  ProviderPolicyResponse,
  ProviderRoutingMode,
  UsageSummaryResponse,
  WebsiteSourceCreateInput,
} from "@support-agent/api-client";

export class DashboardApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "DashboardApiError";
    this.status = status;
  }
}

async function detail(response: Response): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null;
  if (typeof payload?.detail === "string") return payload.detail;
  if (Array.isArray(payload?.detail)) {
    return payload.detail
      .map((item) =>
        typeof item === "object" && item !== null && "msg" in item
          ? String((item as { msg: unknown }).msg)
          : String(item),
      )
      .join(" ");
  }
  return "The request could not be completed.";
}

export async function dashboardRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (init.method && !["GET", "HEAD", "OPTIONS"].includes(init.method.toUpperCase())) {
    headers.set("X-Relay-Request", "dashboard");
  }
  const response = await fetch(`/api/backend${path}`, {
    ...init,
    headers,
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!response.ok) throw new DashboardApiError(response.status, await detail(response));
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function dashboardStream(path: string, init: RequestInit): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "text/event-stream");
  headers.set("Content-Type", "application/json");
  headers.set("X-Relay-Request", "dashboard");
  const response = await fetch(`/api/backend${path}`, {
    ...init,
    headers,
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!response.ok) throw new DashboardApiError(response.status, await detail(response));
  return response;
}

export const dashboardApi = {
  listBots: () => dashboardRequest<BotResponse[]>("/bots"),
  createBot: (payload: BotCreateInput) =>
    dashboardRequest<BotResponse>("/bots", { method: "POST", body: JSON.stringify(payload) }),
  updateBot: (botId: string, payload: BotUpdateInput) =>
    dashboardRequest<BotResponse>(`/bots/${encodeURIComponent(botId)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteBot: (botId: string) =>
    dashboardRequest<void>(`/bots/${encodeURIComponent(botId)}`, { method: "DELETE" }),
  listBotKeys: (botId: string) =>
    dashboardRequest<BotKeyResponse[]>(`/bots/${encodeURIComponent(botId)}/keys`),
  createBotKey: (botId: string, payload: BotKeyCreateInput) =>
    dashboardRequest<BotKeyResponse>(`/bots/${encodeURIComponent(botId)}/keys`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateBotKey: (botId: string, keyId: string, payload: BotKeyUpdateInput) =>
    dashboardRequest<BotKeyResponse>(
      `/bots/${encodeURIComponent(botId)}/keys/${encodeURIComponent(keyId)}`,
      { method: "PATCH", body: JSON.stringify(payload) },
    ),
  revokeBotKey: (botId: string, keyId: string) =>
    dashboardRequest<void>(
      `/bots/${encodeURIComponent(botId)}/keys/${encodeURIComponent(keyId)}`,
      { method: "DELETE" },
    ),
  listSources: (botId: string) =>
    dashboardRequest<KnowledgeSourceResponse[]>(
      `/bots/${encodeURIComponent(botId)}/sources`,
    ),
  uploadFile: (botId: string, file: File, name?: string) => {
    const body = new FormData();
    body.set("file", file);
    if (name?.trim()) body.set("name", name.trim());
    return dashboardRequest<KnowledgeSourceResponse>(
      `/bots/${encodeURIComponent(botId)}/sources/files`,
      { method: "POST", body },
    );
  },
  createWebsite: (botId: string, payload: WebsiteSourceCreateInput) =>
    dashboardRequest<KnowledgeSourceResponse>(
      `/bots/${encodeURIComponent(botId)}/sources/websites`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  createManual: (botId: string, payload: ManualSourceCreateInput) =>
    dashboardRequest<KnowledgeSourceResponse>(
      `/bots/${encodeURIComponent(botId)}/sources/manual`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  updateManual: (sourceId: string, payload: ManualSourceUpdateInput) =>
    dashboardRequest<KnowledgeSourceResponse>(
      `/sources/${encodeURIComponent(sourceId)}/manual`,
      { method: "PATCH", body: JSON.stringify(payload) },
    ),
  deleteSource: (sourceId: string) =>
    dashboardRequest<void>(`/sources/${encodeURIComponent(sourceId)}`, { method: "DELETE" }),
  createPlaygroundSession: (botId: string) =>
    dashboardRequest<PlaygroundSessionResponse>("/playground/sessions", {
      method: "POST",
      body: JSON.stringify({ bot_id: botId }),
    }),
  usageSummary: (botId?: string) =>
    dashboardRequest<UsageSummaryResponse>(
      `/usage/summary${botId ? `?bot_id=${encodeURIComponent(botId)}` : ""}`,
    ),
  listProviderCatalog: () =>
    dashboardRequest<ProviderCatalogEntry[]>("/providers/catalog"),
  listProviderCredentials: () =>
    dashboardRequest<ProviderCredentialResponse[]>("/providers/credentials"),
  createProviderCredential: (payload: ProviderCredentialCreateInput) =>
    dashboardRequest<ProviderCredentialResponse>("/providers/credentials", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  discoverCustomProviderModels: (baseUrl: string, apiKey: string) =>
    dashboardRequest<string[]>("/providers/custom/models", {
      method: "POST",
      body: JSON.stringify({ base_url: baseUrl, api_key: apiKey }),
    }),
  verifyProviderCredential: (credentialId: string) =>
    dashboardRequest<ProviderCredentialResponse>(
      `/providers/credentials/${encodeURIComponent(credentialId)}/verify`,
      { method: "POST" },
    ),
  rotateProviderCredential: (credentialId: string, apiKey: string) =>
    dashboardRequest<ProviderCredentialResponse>(
      `/providers/credentials/${encodeURIComponent(credentialId)}/secret`,
      { method: "PUT", body: JSON.stringify({ api_key: apiKey }) },
    ),
  revokeProviderCredential: (credentialId: string) =>
    dashboardRequest<void>(
      `/providers/credentials/${encodeURIComponent(credentialId)}`,
      { method: "DELETE" },
    ),
  getProviderPolicy: () => dashboardRequest<ProviderPolicyResponse>("/providers/policy"),
  deleteAccount: (password: string) => dashboardRequest<void>("/account/delete", { method: "POST", body: JSON.stringify({ password, confirmation: "DELETE MY ACCOUNT" }) }),
  listChannels: () => dashboardRequest<ChannelInstallationResponse[]>("/channels"),
  installChannel: (payload: ChannelInstallInput) =>
    dashboardRequest<ChannelInstallationResponse>("/channels", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateChannel: (channelId: string, status: ChannelStatus) =>
    dashboardRequest<ChannelInstallationResponse>(`/channels/${encodeURIComponent(channelId)}`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
  revokeChannel: (channelId: string) =>
    dashboardRequest<void>(`/channels/${encodeURIComponent(channelId)}`, { method: "DELETE" }),
  listVoiceAgents: () => dashboardRequest<VoiceAgentResponse[]>("/voice"),
  installVoiceAgent: (payload: VoiceInstallInput) =>
    dashboardRequest<VoiceAgentResponse>("/voice", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateVoiceAgent: (voiceId: string, status: VoiceStatus) =>
    dashboardRequest<VoiceAgentResponse>(`/voice/${encodeURIComponent(voiceId)}`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
  updateProviderPolicy: (mode: ProviderRoutingMode, credentialOrder: string[]) =>
    dashboardRequest<ProviderPolicyResponse>("/providers/policy", {
      method: "PATCH",
      body: JSON.stringify({ mode, credential_order: credentialOrder }),
    }),
};
