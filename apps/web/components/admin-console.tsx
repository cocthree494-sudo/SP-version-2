"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { ArrowIcon, GridIcon, MessageIcon, UserIcon } from "@/components/icons";
import { DashboardApiError, dashboardRequest } from "@/lib/dashboard-api";

type Section = "overview" | "tenants" | "users" | "usage" | "operations" | "audit";

const navigation: Array<{ key: Section; label: string; note: string }> = [
  { key: "overview", label: "Overview", note: "Platform pulse" },
  { key: "tenants", label: "Tenants", note: "Workspaces" },
  { key: "users", label: "Users", note: "Identities" },
  { key: "usage", label: "AI usage", note: "Cost and latency" },
  { key: "operations", label: "Operations", note: "Jobs and health" },
  { key: "audit", label: "Audit log", note: "Immutable record" },
];

interface Summary {
  generated_at: string;
  users: Record<string, number>;
  tenants: Record<string, number>;
  bots: number;
  conversations: number;
  usage: { requests: number; tokens: number; cost_microusd: number; average_latency_ms: number };
  ingestion: Record<string, number>;
  channels: Record<string, number>;
  voice: Record<string, number>;
  security: Record<string, unknown>;
  readiness: Record<string, string>;
  usage_trend: Array<{ day: string; requests: number; tokens: number; cost: number }>;
}

interface Page<T> {
  items: T[];
  page: { page: number; page_size: number; total: number; pages: number };
}

interface TenantRow {
  tenant_id: string; name: string; slug: string; status: string; created_at: string;
  member_count: number; bot_count: number; source_count: number; conversation_count: number;
  token_count: number; estimated_cost_microusd: number; last_activity_at: string | null;
}

interface UserRow {
  user_id: string; email: string; display_name: string | null; status: string;
  email_verified_at: string | null; created_at: string; tenant_count: number;
  last_session_at: string | null; active_session_count: number;
}

interface UsageRow {
  usage_event_id: string; tenant_id: string; tenant_name: string; tenant_slug: string;
  bot_id: string | null; operation: string; provider: string; model: string;
  input_tokens: number; output_tokens: number; latency_ms: number; estimated_cost_microusd: number;
  created_at: string;
}

interface IngestionRow {
  job_id: string; tenant_id: string; tenant_name: string; source_name: string | null;
  job_type: string; state: string; attempts: number; progress_percent: number;
  error_code: string | null; error_message: string | null; created_at: string;
}

interface HealthRow {
  category: "channel" | "voice" | "provider"; resource_id: string; tenant_id: string;
  tenant_name: string; name: string; status: string; detail: Record<string, unknown>;
  updated_at: string | null;
}

interface AuditRow {
  id: string; created_at: string; actor_user_id: string | null; action: string;
  target_type: string; target_id: string | null; reason: string | null; outcome: string;
  request_id: string | null; change_summary: Record<string, unknown>;
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat("en-GB", { notation: value > 9999 ? "compact" : "standard", maximumFractionDigits: 1 }).format(value);
}

function formatCost(microusd: number): string {
  return `$${(microusd / 1_000_000).toFixed(2)}`;
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "Never";
  return new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function StatusBadge({ value }: { value: string }) {
  const tone = ["active", "ready", "connected", "succeeded", "verified"].includes(value)
    ? "ok"
    : ["failed", "error", "disabled", "revoked", "suspended"].includes(value)
      ? "danger"
      : "warn";
  return <span className={`admin-status admin-status-${tone}`}><i />{value.replaceAll("_", " ")}</span>;
}

function Metric({ label, value, detail, tone = "default" }: { label: string; value: string; detail: string; tone?: string }) {
  return <article className={`admin-metric admin-metric-${tone}`}><span>{label}</span><strong>{value}</strong><small>{detail}</small></article>;
}

function ErrorState({ message }: { message: string }) {
  return <div className="admin-empty admin-error"><UserIcon width={18} height={18} /><strong>{message}</strong><span>Refresh the page or check the platform health panel.</span></div>;
}

function LoadingRows() {
  return <div className="admin-loading-rows">{[1, 2, 3, 4].map((item) => <i key={item} />)}</div>;
}

function ActionDialog({ title, description, onClose, onSubmit, loading }: { title: string; description: string; onClose: () => void; onSubmit: (reason: string) => void; loading: boolean }) {
  const [reason, setReason] = useState("");
  return <div className="admin-dialog-backdrop" role="presentation">
    <div className="admin-dialog" role="dialog" aria-modal="true" aria-labelledby="admin-dialog-title">
      <span className="admin-dialog-kicker">Confirm operator action</span>
      <h2 id="admin-dialog-title">{title}</h2>
      <p>{description}</p>
      <label>Reason <textarea value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Record why this action is necessary" autoFocus /></label>
      <div className="admin-dialog-actions"><button className="admin-button admin-button-quiet" type="button" onClick={onClose} disabled={loading}>Cancel</button><button className="admin-button admin-button-danger" type="button" onClick={() => onSubmit(reason)} disabled={loading || reason.trim().length < 3}>{loading ? "Applying..." : "Confirm action"}</button></div>
    </div>
  </div>;
}

function Overview({ summary, rangeDays, onRangeChange, onRefresh }: { summary: Summary; rangeDays: string; onRangeChange: (value: string) => void; onRefresh: () => void }) {
  const maxRequests = Math.max(1, ...summary.usage_trend.map((item) => item.requests));
  return <div className="admin-stack">
    <div className="admin-section-heading"><div><span className="admin-kicker">Relay control plane</span><h1>Platform pulse</h1><p>Live operational evidence across every Relay workspace.</p></div><div className="admin-heading-actions"><select className="admin-range-select" aria-label="Date range" value={rangeDays} onChange={(event) => onRangeChange(event.target.value)}><option value="7">Last 7 days</option><option value="30">Last 30 days</option><option value="90">Last 90 days</option><option value="all">All time</option></select><button className="admin-button admin-button-quiet" type="button" onClick={onRefresh}><ArrowIcon width={15} height={15} />Refresh</button></div></div>
    <section className="admin-metric-grid">
      <Metric label="Active tenants" value={formatNumber(summary.tenants.active ?? 0)} detail={`${formatNumber(summary.tenants.total ?? 0)} total workspaces`} tone="green" />
      <Metric label="Active users" value={formatNumber(summary.users.active ?? 0)} detail={`${formatNumber(summary.users.total ?? 0)} identities`} />
      <Metric label="AI requests" value={formatNumber(summary.usage.requests)} detail={`${formatNumber(summary.usage.tokens)} input/output tokens`} tone="lime" />
      <Metric label="Estimated cost" value={formatCost(summary.usage.cost_microusd)} detail={`${summary.usage.average_latency_ms} ms average latency`} tone="blue" />
    </section>
    <section className="admin-overview-grid">
      <article className="admin-panel admin-trend-panel"><div className="admin-panel-heading"><div><span className="admin-kicker">AI activity</span><h2>Requests over time</h2></div><span className="admin-panel-meta">{formatNumber(summary.usage.requests)} total</span></div><div className="admin-bars">{summary.usage_trend.length ? summary.usage_trend.slice(-14).map((item) => <div className="admin-bar-column" key={item.day} title={`${item.requests} requests`}><span style={{ height: `${Math.max(8, (item.requests / maxRequests) * 100)}%` }} /><small>{new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short" }).format(new Date(item.day))}</small></div>) : <div className="admin-empty"><span>No usage events in this range.</span></div>}</div></article>
      <article className="admin-panel"><div className="admin-panel-heading"><div><span className="admin-kicker">Readiness</span><h2>Systems</h2></div><StatusBadge value="ready" /></div><div className="admin-health-list">{Object.entries(summary.readiness).map(([key, value]) => <div key={key}><span>{key}</span><StatusBadge value={value} /></div>)}<div><span>OTP email</span><StatusBadge value={String(summary.security.otp_email_provider ?? "unknown")} /></div><div><span>Active sessions</span><strong>{formatNumber(Number(summary.security.active_sessions ?? 0))}</strong></div></div></article>
    </section>
    <section className="admin-overview-grid admin-overview-grid-bottom"><article className="admin-panel"><div className="admin-panel-heading"><div><span className="admin-kicker">Queue</span><h2>Ingestion jobs</h2></div><Link href="/admin/operations">Open operations <ArrowIcon width={14} height={14} /></Link></div><div className="admin-split-stats">{Object.entries(summary.ingestion).slice(0, 4).map(([key, value]) => <div key={key}><strong>{formatNumber(value)}</strong><span>{key.replaceAll("_", " ")}</span></div>)}</div></article><article className="admin-panel"><div className="admin-panel-heading"><div><span className="admin-kicker">Connections</span><h2>Channel health</h2></div><Link href="/admin/operations">Inspect <ArrowIcon width={14} height={14} /></Link></div><div className="admin-split-stats">{Object.entries({ ...summary.channels, ...summary.voice }).slice(0, 4).map(([key, value]) => <div key={key}><strong>{formatNumber(value)}</strong><span>{key.replaceAll("_", " ")}</span></div>)}</div></article></section>
  </div>;
}

export function AdminConsole({ section }: { section: Section }) {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [rows, setRows] = useState<Page<TenantRow | UserRow | UsageRow | IngestionRow | AuditRow> | null>(null);
  const [health, setHealth] = useState<Page<HealthRow> | null>(null);
  const [query, setQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [rangeDays, setRangeDays] = useState("30");
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [action, setAction] = useState<{ kind: "tenant" | "user" | "sessions"; id: string; desired?: string } | null>(null);
  const [actionLoading, setActionLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      if (section === "overview") {
        const summaryPath = rangeDays === "all"
          ? "/admin/summary"
          : `/admin/summary?start=${encodeURIComponent(new Date(Date.now() - Number(rangeDays) * 86_400_000).toISOString())}`;
        setSummary(await dashboardRequest<Summary>(summaryPath));
        return;
      }
      if (section === "operations") { setHealth(await dashboardRequest<Page<HealthRow>>(`/admin/health?page=${page}&page_size=25`)); return; }
      const endpoint = section === "audit" ? "audit" : section === "usage" ? "usage" : section;
      const params = new URLSearchParams({ page: String(page), page_size: "25" });
      if (appliedQuery) params.set("q", appliedQuery);
      if (statusFilter && (section === "tenants" || section === "users")) params.set("status", statusFilter);
      setRows(await dashboardRequest<Page<TenantRow | UserRow | UsageRow | IngestionRow | AuditRow>>(`/admin/${endpoint}?${params.toString()}`));
    } catch (caught) {
      setError(caught instanceof DashboardApiError && caught.status === 403 ? "This account is not approved for platform administration." : caught instanceof Error ? caught.message : "The admin service is unavailable.");
    } finally { setLoading(false); }
  }, [appliedQuery, page, rangeDays, section, statusFilter]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { setPage(1); }, [section]);

  const sectionMeta = navigation.find((item) => item.key === section) ?? navigation[0];
  const submitAction = async (reason: string) => {
    if (!action) return;
    setActionLoading(true);
    try {
      const body = JSON.stringify({ status: action.desired ?? "active", reason, confirmation: "CONFIRM", idempotency_key: `${action.kind}-${action.id}-${Date.now()}` });
      if (action.kind === "sessions") await dashboardRequest(`/admin/users/${action.id}/revoke-sessions`, { method: "POST", body });
      else await dashboardRequest(`/admin/${action.kind === "tenant" ? "tenants" : "users"}/${action.id}/status`, { method: "POST", body });
      setAction(null); await load();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "The action could not be completed."); } finally { setActionLoading(false); }
  };

  return <div className="admin-app">
    <aside className="admin-sidebar"><div className="admin-brand"><span className="admin-brand-mark">R</span><div><strong>Relay</strong><small>Control plane</small></div></div><div className="admin-sidebar-label">Operate</div><nav aria-label="Platform administration">{navigation.map((item) => <Link key={item.key} href={`/admin${item.key === "overview" ? "" : `/${item.key}`}`} className={section === item.key ? "admin-nav-link admin-nav-link-active" : "admin-nav-link"}><span className="admin-nav-icon">{item.key === "overview" ? <GridIcon width={16} height={16} /> : item.key === "users" ? <UserIcon width={16} height={16} /> : item.key === "audit" ? <UserIcon width={16} height={16} /> : <MessageIcon width={16} height={16} />}</span><span><strong>{item.label}</strong><small>{item.note}</small></span></Link>)}</nav><div className="admin-sidebar-footer"><span className="admin-live-dot" />Private operator access<Link href="/dashboard">Back to workspace <ArrowIcon width={13} height={13} /></Link></div></aside>
    <main className="admin-main"><header className="admin-topbar"><div><span className="admin-topbar-kicker">Relay / Platform administration</span><strong>{sectionMeta.label}</strong></div><div className="admin-topbar-right"><span className="admin-secure-pill"><i />OTP session verified</span><span className="admin-avatar">A</span></div></header><div className="admin-content">{loading && section !== "overview" ? <LoadingRows /> : error ? <ErrorState message={error} /> : section === "overview" && summary ? <Overview summary={summary} rangeDays={rangeDays} onRangeChange={setRangeDays} onRefresh={() => void load()} /> : section === "operations" && health ? <Operations health={health} /> : rows ? <DataSection section={section} data={rows} query={query} setQuery={setQuery} statusFilter={statusFilter} setStatusFilter={setStatusFilter} onSearch={() => { setPage(1); setAppliedQuery(query.trim()); }} onAction={setAction} /> : null}<Pagination page={section === "operations" ? health?.page : rows?.page} onPage={setPage} /></div></main>{action ? <ActionDialog title={action.kind === "sessions" ? "Revoke all user sessions" : action.desired === "active" ? `Reactivate ${action.kind}` : action.kind === "user" ? "Disable user" : "Suspend tenant"} description={action.kind === "sessions" ? "Every active browser session and refresh token for this identity will be invalidated." : "This changes the account lifecycle state across the platform and is recorded in the immutable audit log."} onClose={() => setAction(null)} onSubmit={submitAction} loading={actionLoading} /> : null}</div>;
}

function DataSection({ section, data, query, setQuery, statusFilter, setStatusFilter, onSearch, onAction }: { section: Section; data: Page<TenantRow | UserRow | UsageRow | IngestionRow | AuditRow>; query: string; setQuery: (value: string) => void; statusFilter: string; setStatusFilter: (value: string) => void; onSearch: () => void; onAction: (value: { kind: "tenant" | "user" | "sessions"; id: string; desired?: string }) => void }) {
  return <div className="admin-stack"><div className="admin-section-heading"><div><span className="admin-kicker">{section === "audit" ? "Immutable record" : "Cross-tenant reporting"}</span><h1>{navigation.find((item) => item.key === section)?.label}</h1><p>{section === "audit" ? "Every platform read and mutation, with redacted context." : "Search, inspect, and act on live platform data."}</p></div></div><div className="admin-toolbar"><form onSubmit={(event) => { event.preventDefault(); onSearch(); }}><input aria-label="Search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={`Search ${section}...`} /><button className="admin-button admin-button-dark" type="submit">Search</button></form>{section === "tenants" || section === "users" ? <select aria-label="Filter status" value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); }}><option value="">All statuses</option><option value="active">Active</option><option value={section === "tenants" ? "suspended" : "disabled"}>{section === "tenants" ? "Suspended" : "Disabled"}</option></select> : null}</div><div className="admin-table-wrap"><table className="admin-table"><thead><tr>{section === "tenants" ? <><th>Workspace</th><th>Status</th><th>Members</th><th>Bots</th><th>AI cost</th><th>Last activity</th><th /></> : section === "users" ? <><th>Identity</th><th>Status</th><th>Workspaces</th><th>Sessions</th><th>Last session</th><th /></> : section === "usage" ? <><th>Tenant</th><th>Provider / model</th><th>Operation</th><th>Tokens</th><th>Latency</th><th>Cost</th><th>Created</th></> : <><th>Time</th><th>Action</th><th>Target</th><th>Outcome</th><th>Reason</th></>}</tr></thead><tbody>{data.items.map((item) => <DataRow key={"id" in item ? item.id : "usage_event_id" in item ? item.usage_event_id : "job_id" in item ? item.job_id : "tenant_id" in item ? item.tenant_id : item.user_id} section={section} item={item} onAction={onAction} />)}</tbody></table>{data.items.length === 0 ? <div className="admin-empty"><span>No records match this view.</span></div> : null}</div></div>;
}

function DataRow({ section, item, onAction }: { section: Section; item: TenantRow | UserRow | UsageRow | IngestionRow | AuditRow; onAction: (value: { kind: "tenant" | "user" | "sessions"; id: string; desired?: string }) => void }) {
  if (section === "tenants") { const row = item as TenantRow; return <tr><td><strong>{row.name}</strong><small>{row.slug} / {row.member_count} members</small></td><td><StatusBadge value={row.status} /></td><td>{formatNumber(row.member_count)}</td><td>{formatNumber(row.bot_count)}</td><td>{formatCost(row.estimated_cost_microusd)}</td><td>{formatDate(row.last_activity_at)}</td><td><button className="admin-row-action" type="button" onClick={() => onAction({ kind: "tenant", id: row.tenant_id, desired: row.status === "active" ? "suspended" : "active" })}>{row.status === "active" ? "Suspend" : "Reactivate"}</button></td></tr>; }
  if (section === "users") { const row = item as UserRow; return <tr><td><strong>{row.display_name || row.email.split("@")[0]}</strong><small>{row.email}</small></td><td><StatusBadge value={row.status} /></td><td>{formatNumber(row.tenant_count)}</td><td>{formatNumber(row.active_session_count)}</td><td>{formatDate(row.last_session_at)}</td><td><div className="admin-row-actions"><button className="admin-row-action" type="button" onClick={() => onAction({ kind: "user", id: row.user_id, desired: row.status === "active" ? "disabled" : "active" })}>{row.status === "active" ? "Disable" : "Reactivate"}</button><button className="admin-row-action admin-row-action-muted" type="button" onClick={() => onAction({ kind: "sessions", id: row.user_id })}>Revoke sessions</button></div></td></tr>; }
  if (section === "usage") { const row = item as UsageRow; return <tr><td><strong>{row.tenant_name}</strong><small>{row.tenant_slug}</small></td><td><strong>{row.provider}</strong><small>{row.model}</small></td><td><StatusBadge value={row.operation} /></td><td>{formatNumber(row.input_tokens + row.output_tokens)}</td><td>{row.latency_ms} ms</td><td>{formatCost(row.estimated_cost_microusd)}</td><td>{formatDate(row.created_at)}</td></tr>; }
  const row = item as AuditRow; return <tr><td>{formatDate(row.created_at)}</td><td><strong>{row.action}</strong><small>{row.actor_user_id || "system"}</small></td><td><strong>{row.target_type}</strong><small>{row.target_id || "platform"}</small></td><td><StatusBadge value={row.outcome} /></td><td>{row.reason || "-"}</td></tr>;
}

function Operations({ health }: { health: Page<HealthRow> }) {
  return <div className="admin-stack"><div className="admin-section-heading"><div><span className="admin-kicker">Operational surface</span><h1>Operations</h1><p>Connection health and runtime signals without customer content or secrets.</p></div></div><div className="admin-health-grid">{health.items.map((item) => <article className="admin-health-card" key={item.resource_id}><div className="admin-health-card-top"><span className="admin-health-type">{item.category}</span><StatusBadge value={item.status} /></div><h2>{item.name}</h2><p>{item.tenant_name}</p><dl>{Object.entries(item.detail).filter(([, value]) => value !== null && value !== undefined).slice(0, 3).map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{String(value)}</dd></div>)}</dl><small>{formatDate(item.updated_at)}</small></article>)}</div>{health.items.length === 0 ? <div className="admin-empty"><span>No health records have been provisioned yet.</span></div> : null}</div>;
}

function Pagination({ page, onPage }: { page: { page: number; pages: number } | undefined; onPage: (value: number) => void }) {
  if (!page || page.pages <= 1) return null;
  return <div className="admin-pagination"><button className="admin-button admin-button-quiet" type="button" disabled={page.page <= 1} onClick={() => onPage(page.page - 1)}>Previous</button><span>Page {page.page} of {page.pages}</span><button className="admin-button admin-button-quiet" type="button" disabled={page.page >= page.pages} onClick={() => onPage(page.page + 1)}>Next</button></div>;
}
