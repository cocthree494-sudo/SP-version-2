export const API_VERSION = "v1" as const;

export type ApiVersion = typeof API_VERSION;

export type MembershipRole = "owner" | "admin" | "member";
export type AccountStatus = "active" | "disabled";
export type TenantStatus = "active" | "suspended";

export interface TokenPairResponse {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
}

export interface RegisterInput {
  email: string;
  password: string;
  display_name?: string;
  organization_name: string;
  organization_slug?: string;
}

export interface LoginInput {
  email: string;
  password: string;
  organization_slug?: string;
}

export interface CurrentTenant {
  id: string;
  name: string;
  slug: string;
  status: TenantStatus;
}

export interface MeResponse {
  id: string;
  email: string;
  display_name: string | null;
  status: AccountStatus;
  created_at: string;
  tenant: CurrentTenant;
  role: MembershipRole;
}

export type BotStatus = "active" | "disabled";

export interface BotResponse {
  id: string;
  name: string;
  system_policy: string | null;
  default_language: string;
  status: BotStatus;
  widget_welcome_text: string;
  widget_accent_color: string;
  widget_position: "left" | "right";
  created_at: string;
  updated_at: string;
}

export interface BotCreateInput {
  name: string;
  system_policy?: string | null;
  default_language?: string;
  status?: BotStatus;
  widget_welcome_text?: string;
  widget_accent_color?: string;
  widget_position?: "left" | "right";
}

export interface BotUpdateInput {
  name?: string;
  system_policy?: string | null;
  default_language?: string;
  status?: BotStatus;
  widget_welcome_text?: string;
  widget_accent_color?: string;
  widget_position?: "left" | "right";
}

export interface BotKeyResponse {
  id: string;
  bot_id: string;
  publishable_key: string;
  label: string;
  allowed_origins: string[];
  revoked_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface BotKeyCreateInput {
  label?: string;
  allowed_origins: string[];
}

export interface BotKeyUpdateInput {
  label?: string;
  allowed_origins?: string[];
}

export type KnowledgeSourceType = "file" | "website" | "manual";
export type KnowledgeSourceStatus =
  | "pending"
  | "processing"
  | "ready"
  | "failed"
  | "deleting";

export interface KnowledgeSourceResponse {
  id: string;
  bot_id: string;
  type: KnowledgeSourceType;
  name: string;
  status: KnowledgeSourceStatus;
  details: Record<string, unknown>;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface WebsiteSourceCreateInput {
  url: string;
  name?: string;
  max_pages?: number;
  max_depth?: number;
  request_delay_seconds?: number;
}

export interface ManualSourceCreateInput {
  question: string;
  answer: string;
  name?: string;
}

export interface ManualSourceUpdateInput {
  question?: string;
  answer?: string;
  name?: string;
}

export interface PlaygroundSessionResponse {
  conversation_id: string;
}

export interface UsageBreakdownResponse {
  operation: "generation" | "embedding";
  provider: string;
  model: string;
  event_count: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  total_tokens: number;
  total_latency_ms: number;
  estimated_cost_microusd: number;
}

export interface UsageSummaryResponse {
  start: string | null;
  end: string | null;
  bot_id: string | null;
  event_count: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  total_tokens: number;
  total_latency_ms: number;
  average_latency_ms: number;
  estimated_cost_microusd: number;
  by_model: UsageBreakdownResponse[];
}

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

function errorDetail(payload: unknown): string {
  if (typeof payload === "object" && payload !== null && "detail" in payload) {
    const detail = (payload as { detail: unknown }).detail;
    if (typeof detail === "string") {
      return detail;
    }
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          if (typeof item === "object" && item !== null && "msg" in item) {
            return String((item as { msg: unknown }).msg);
          }
          return String(item);
        })
        .join(" ");
    }
  }
  return "The API could not complete this request.";
}

export class SupportAgentApiClient {
  readonly baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  private async request<T>(
    path: string,
    init: RequestInit,
    accessToken?: string,
  ): Promise<T> {
    const response = await fetch(`${this.baseUrl}/${API_VERSION}${path}`, {
      ...init,
      cache: "no-store",
      headers: {
        Accept: "application/json",
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        ...init.headers,
      },
    });
    const payload: unknown = await response.json().catch(() => null);
    if (!response.ok) {
      throw new ApiError(response.status, errorDetail(payload));
    }
    return payload as T;
  }

  register(payload: RegisterInput): Promise<TokenPairResponse> {
    return this.request<TokenPairResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  login(payload: LoginInput): Promise<TokenPairResponse> {
    return this.request<TokenPairResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  refresh(refreshToken: string): Promise<TokenPairResponse> {
    return this.request<TokenPairResponse>("/auth/refresh", {
      method: "POST",
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
  }

  me(accessToken: string): Promise<MeResponse> {
    return this.request<MeResponse>("/me", { method: "GET" }, accessToken);
  }

  listBots(accessToken: string): Promise<BotResponse[]> {
    return this.request<BotResponse[]>("/bots", { method: "GET" }, accessToken);
  }

  createBot(accessToken: string, payload: BotCreateInput): Promise<BotResponse> {
    return this.request<BotResponse>(
      "/bots",
      { method: "POST", body: JSON.stringify(payload) },
      accessToken,
    );
  }

  updateBot(
    accessToken: string,
    botId: string,
    payload: BotUpdateInput,
  ): Promise<BotResponse> {
    return this.request<BotResponse>(
      `/bots/${encodeURIComponent(botId)}`,
      { method: "PATCH", body: JSON.stringify(payload) },
      accessToken,
    );
  }

  async deleteBot(accessToken: string, botId: string): Promise<void> {
    await this.request<null>(
      `/bots/${encodeURIComponent(botId)}`,
      { method: "DELETE" },
      accessToken,
    );
  }

  listSources(accessToken: string, botId: string): Promise<KnowledgeSourceResponse[]> {
    return this.request<KnowledgeSourceResponse[]>(
      `/bots/${encodeURIComponent(botId)}/sources`,
      { method: "GET" },
      accessToken,
    );
  }

  createWebsiteSource(
    accessToken: string,
    botId: string,
    payload: WebsiteSourceCreateInput,
  ): Promise<KnowledgeSourceResponse> {
    return this.request<KnowledgeSourceResponse>(
      `/bots/${encodeURIComponent(botId)}/sources/websites`,
      { method: "POST", body: JSON.stringify(payload) },
      accessToken,
    );
  }

  createManualSource(
    accessToken: string,
    botId: string,
    payload: ManualSourceCreateInput,
  ): Promise<KnowledgeSourceResponse> {
    return this.request<KnowledgeSourceResponse>(
      `/bots/${encodeURIComponent(botId)}/sources/manual`,
      { method: "POST", body: JSON.stringify(payload) },
      accessToken,
    );
  }

  updateManualSource(
    accessToken: string,
    sourceId: string,
    payload: ManualSourceUpdateInput,
  ): Promise<KnowledgeSourceResponse> {
    return this.request<KnowledgeSourceResponse>(
      `/sources/${encodeURIComponent(sourceId)}/manual`,
      { method: "PATCH", body: JSON.stringify(payload) },
      accessToken,
    );
  }

  async deleteSource(accessToken: string, sourceId: string): Promise<void> {
    await this.request<null>(
      `/sources/${encodeURIComponent(sourceId)}`,
      { method: "DELETE" },
      accessToken,
    );
  }
}

export function createApiClient(baseUrl: string): SupportAgentApiClient {
  return new SupportAgentApiClient(baseUrl);
}
