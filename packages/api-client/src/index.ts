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

export interface AuthChallengeResponse {
  status: "otp_required";
  challenge_id: string;
  email_hint: string;
  flow: "login" | "register";
  expires_in: number;
  resend_after: number;
}

export interface PendingAuthResponse {
  status: "otp_required";
  email_hint: string;
  flow: "login" | "register";
  expires_in: number;
  resend_after: number;
}

export interface AuthOtpChallengeInput {
  challenge_id: string;
}

export interface AuthOtpVerifyInput extends AuthOtpChallengeInput {
  code: string;
}

export type SocialProvider = "google" | "microsoft" | "github";
export type SocialAuthMode = "login" | "register";

export interface SocialAuthStartInput {
  mode: SocialAuthMode;
  organization_slug?: string;
}

export interface SocialAuthStartResponse {
  provider: SocialProvider;
  authorization_url: string;
}

export interface SocialAuthCallbackInput {
  code: string;
  state: string;
}

export type SocialAuthStatus =
  | "otp_required"
  | "organization_required"
  | "organization_selection_required"
  | "account_link_required";

export interface SocialAuthResponse {
  status: SocialAuthStatus;
  expires_in: number | null;
  continuation_token: string | null;
  email: string | null;
  display_name: string | null;
  organizations: CurrentTenant[];
  challenge_id: string | null;
  email_hint: string | null;
  flow: "login" | "register" | null;
  resend_after: number | null;
}

export interface SocialAuthCompleteInput {
  continuation_token: string;
  organization_name?: string;
  organization_slug?: string;
}

export interface SocialAuthLinkInput {
  continuation_token: string;
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
  email_verified_at: string | null;
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

export type GenerationProvider =
  | "ai-gateway" | "alibaba" | "alibaba-coding-plan" | "anthropic" | "arcee" | "actual"
  | "azure-foundry" | "bedrock" | "copilot" | "copilot-acp" | "custom" | "deepseek"
  | "fireworks" | "gmi" | "gemini" | "huggingface" | "kilocode" | "kimi" | "kimi-cn"
  | "lmstudio" | "minimax" | "minimax-cn" | "minimax-oauth" | "novita" | "nvidia"
  | "nous-portal" | "openai" | "openai-codex" | "openrouter" | "opencode-go" | "opencode-zen"
  | "ollama-cloud" | "qwen-oauth" | "stepfun" | "tencent-tokenhub" | "xai" | "xai-oauth"
  | "xiaomi" | "vertex" | "zai";
export type ProviderCredentialStatus = "unverified" | "verified" | "invalid" | "revoked";
export type ProviderRoutingMode =
  | "platform_only"
  | "tenant_first_with_platform_fallback"
  | "tenant_only";

export interface ProviderCredentialResponse {
  id: string;
  provider: GenerationProvider;
  label: string;
  base_url: string | null;
  masked_secret: string;
  low_cost_model_id: string;
  strong_model_id: string | null;
  status: ProviderCredentialStatus;
  verified_at: string | null;
  rotated_at: string | null;
  revoked_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProviderCredentialCreateInput {
  provider: GenerationProvider;
  label: string;
  api_key: string;
  base_url?: string | null;
  low_cost_model_id: string;
  strong_model_id?: string | null;
}

export type ChannelType =
  | "telegram_personal"
  | "whatsapp_business"
  | "facebook_page"
  | "email";
export type ChannelStatus = "pending" | "connected" | "paused" | "revoked" | "error";

export interface ChannelInstallationResponse {
  id: string;
  bot_id: string | null;
  channel_type: ChannelType;
  external_identity: string;
  status: ChannelStatus;
  conversation_scope: string[];
  consent_record: Record<string, unknown>;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChannelInstallInput {
  channel_type: ChannelType;
  bot_id: string;
  external_identity: string;
  conversation_scope?: string[];
  consent_acknowledged: boolean;
}

export type VoiceStatus = "pending" | "ready" | "paused" | "error";

export interface VoiceAgentResponse {
  id: string;
  bot_id: string | null;
  provider: "twilio" | "sip";
  phone_number: string;
  language: string;
  voice: string;
  business_hours: Record<string, unknown>;
  outbound_enabled: boolean;
  recording_enabled: boolean;
  retention_days: number;
  monthly_cost_limit_usd: number;
  status: VoiceStatus;
  created_at: string;
  updated_at: string;
}

export interface VoiceInstallInput {
  bot_id?: string | null;
  provider?: "twilio" | "sip";
  phone_number: string;
  language?: string;
  voice?: string;
  business_hours?: Record<string, unknown>;
  outbound_enabled?: boolean;
  recording_enabled?: boolean;
  retention_days?: number;
  monthly_cost_limit_usd?: number;
  consent_acknowledged: boolean;
  outbound_consent?: boolean;
  recording_consent?: boolean;
}

export interface ProviderCatalogModel {
  id: string;
  label: string;
}

export interface ProviderCatalogEntry {
  id: string;
  label: string;
  aliases: string[];
  setup_method: "api_key" | "oauth" | "cloud_account" | "local_endpoint" | "custom_endpoint";
  credential_env: string | null;
  model_discovery: "live" | "maintained" | "oauth" | "local";
  enabled: boolean;
  availability_reason: string | null;
  models: ProviderCatalogModel[];
}

export interface ProviderPolicyResponse {
  mode: ProviderRoutingMode;
  credential_order: string[];
}

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  readonly retryAfter: number | null;

  constructor(status: number, detail: string, retryAfter: number | null = null) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.retryAfter = retryAfter;
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
      const retryAfterValue = response.headers.get("retry-after");
      const retryAfter = retryAfterValue === null ? null : Number.parseInt(retryAfterValue, 10);
      throw new ApiError(
        response.status,
        errorDetail(payload),
        Number.isFinite(retryAfter) ? retryAfter : null,
      );
    }
    return payload as T;
  }

  register(payload: RegisterInput, headers?: HeadersInit): Promise<AuthChallengeResponse> {
    return this.request<AuthChallengeResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
      headers,
    });
  }

  login(payload: LoginInput, headers?: HeadersInit): Promise<AuthChallengeResponse> {
    return this.request<AuthChallengeResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify(payload),
      headers,
    });
  }

  socialStart(
    provider: SocialProvider,
    payload: SocialAuthStartInput,
  ): Promise<SocialAuthStartResponse> {
    return this.request<SocialAuthStartResponse>(
      `/auth/oauth/${encodeURIComponent(provider)}/start`,
      { method: "POST", body: JSON.stringify(payload) },
    );
  }

  socialCallback(
    provider: SocialProvider,
    payload: SocialAuthCallbackInput,
    headers?: HeadersInit,
  ): Promise<SocialAuthResponse> {
    return this.request<SocialAuthResponse>(
      `/auth/oauth/${encodeURIComponent(provider)}/callback`,
      { method: "POST", body: JSON.stringify(payload), headers },
    );
  }

  socialRegister(
    payload: SocialAuthCompleteInput,
    headers?: HeadersInit,
  ): Promise<AuthChallengeResponse> {
    return this.request<AuthChallengeResponse>(
      "/auth/oauth/register",
      { method: "POST", body: JSON.stringify(payload), headers },
    );
  }

  socialSelect(
    payload: SocialAuthCompleteInput,
    headers?: HeadersInit,
  ): Promise<AuthChallengeResponse> {
    return this.request<AuthChallengeResponse>(
      "/auth/oauth/select",
      { method: "POST", body: JSON.stringify(payload), headers },
    );
  }

  otpStatus(payload: AuthOtpChallengeInput): Promise<AuthChallengeResponse> {
    return this.request<AuthChallengeResponse>("/auth/otp/status", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  otpCancel(payload: AuthOtpChallengeInput): Promise<void> {
    return this.request<void>("/auth/otp/cancel", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  otpResend(
    payload: AuthOtpChallengeInput,
    headers?: HeadersInit,
  ): Promise<AuthChallengeResponse> {
    return this.request<AuthChallengeResponse>("/auth/otp/resend", {
      method: "POST",
      body: JSON.stringify(payload),
      headers,
    });
  }

  otpVerify(payload: AuthOtpVerifyInput): Promise<TokenPairResponse> {
    return this.request<TokenPairResponse>("/auth/otp/verify", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  socialLink(
    accessToken: string,
    payload: SocialAuthLinkInput,
  ): Promise<void> {
    return this.request<void>(
      "/auth/oauth/link",
      { method: "POST", body: JSON.stringify(payload) },
      accessToken,
    );
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
