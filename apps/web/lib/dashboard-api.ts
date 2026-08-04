import type {
  BotCreateInput,
  BotResponse,
  BotUpdateInput,
  KnowledgeSourceResponse,
  ManualSourceCreateInput,
  ManualSourceUpdateInput,
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
};
