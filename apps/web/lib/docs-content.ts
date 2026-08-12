export interface DocumentationSection {
  id: string;
  title: string;
  summary: string;
  topics: string[];
  steps: string[];
}

export const documentationSections: DocumentationSection[] = [
  {
    id: "getting-started",
    title: "Getting started",
    summary: "Create a workspace, invite the right teammates, and add your first support bot.",
    topics: ["workspace", "roles", "bot"],
    steps: ["Create or sign in to your workspace with email, Google, Microsoft, or GitHub.", "Create a bot, then add trusted knowledge before publishing it.", "Use the Overview page to confirm your bot, provider, and usage health."],
  },
  {
    id: "account-security",
    title: "Account and security",
    summary: "Keep tenant access explicit, review account details, and delete an account safely.",
    topics: ["login", "sign out", "delete account", "same email"],
    steps: ["Open your profile menu to review the current user, workspace, and role.", "Use the explicit Sign out action when leaving a shared device.", "Account deletion requires your password and typing DELETE MY ACCOUNT; the same email can register again after deletion."],
  },
  {
    id: "providers",
    title: "Providers and routing",
    summary: "Connect an approved generation provider, choose its model dropdown, and set a tenant routing policy.",
    topics: ["API key", "model", "fallback", "custom provider"],
    steps: ["Open Providers and search the catalog, then choose an enabled provider.", "Select the low-cost and strong models from the provider-provided dropdowns; API-key providers require no typed model URL.", "For Custom Endpoint, use an HTTPS URL, discover its models, and choose tenant-first or tenant-only routing after verification."],
  },
  {
    id: "custom-provider-safety",
    title: "Custom endpoint safety",
    summary: "Custom providers are protected against local-network, metadata, redirect, and oversized-response abuse.",
    topics: ["SSRF", "HTTPS", "model discovery", "private IP"],
    steps: ["Use a public HTTPS endpoint with no credentials, query string, or fragment.", "The service resolves the host and rejects private, loopback, link-local, multicast, and cloud metadata addresses.", "Only bounded model IDs are returned; your API key is write-only and never appears in the response."],
  },
  {
    id: "bots-knowledge-widget",
    title: "Bots, knowledge, and widget",
    summary: "Shape each answer from trusted sources, then publish the support widget to allowed origins.",
    topics: ["knowledge", "widget", "allowed origins", "publishable key"],
    steps: ["Create a bot and upload files, websites, or manual question-and-answer sources.", "Wait for knowledge processing to become ready before relying on it in production.", "Configure the widget greeting, accent, launcher position, publishable key, and exact allowed origins."],
  },
  {
    id: "channels",
    title: "Channel connections",
    summary: "Connect the customer inboxes where the agent is allowed to read and reply.",
    topics: ["Telegram", "WhatsApp", "Facebook", "email", "scope"],
    steps: ["Use Channels to select Telegram personal, WhatsApp Business, Facebook Page, or email.", "Telegram personal connections use a provider-owned QR/OTP flow; OTPs never go into this dashboard.", "WhatsApp requires the official Business API and Facebook Messenger requires a tenant-owned Page; select a conversation scope and consent explicitly."],
  },
  {
    id: "voice",
    title: "Voice call agent",
    summary: "Configure voice support with clear consent, interruption handling, and a tenant-level cost boundary.",
    topics: ["telephony", "recording", "outbound", "cost limit"],
    steps: ["Choose an approved Twilio or SIP mode and add an international phone number.", "Outbound calls and recording are opt-in controls with separate consent; recording is off and retention is zero by default.", "Verify the provider webhook contract before marking a voice agent ready for live calls."],
  },
  {
    id: "routing-and-usage",
    title: "Routing and usage",
    summary: "Understand provider fallback and keep an eye on latency, tokens, and estimated cost.",
    topics: ["platform only", "tenant only", "fallback", "usage"],
    steps: ["Platform only uses managed credentials; tenant only prevents platform fallback when no verified tenant key exists.", "Tenant first with platform fallback tries your verified credentials before the managed platform route.", "Use usage summaries to inspect events, token totals, latency, and estimated spend by model."],
  },
  {
    id: "troubleshooting",
    title: "Troubleshooting",
    summary: "Resolve the most common setup and connection issues without exposing secrets.",
    topics: ["OAuth", "502", "verification", "pending"],
    steps: ["If social sign-in says it is not configured, the workspace administrator must add the provider client credentials and exact callback URL.", "If a provider remains pending, verify the credential from Providers and check that its model is selected from the catalog.", "A 502 at OAuth usually means the host cannot reach the API or the callback/domain configuration is stale; check the live API health and deployment logs."],
  },
];
