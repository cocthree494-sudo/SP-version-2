"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import type { BotResponse, ChannelInstallationResponse, ChannelStatus, ChannelType } from "@support-agent/api-client";

import { ArrowIcon, MessageIcon, PlusIcon } from "@/components/icons";
import { DashboardApiError, dashboardApi } from "@/lib/dashboard-api";

const channelOptions: Array<{
  type: ChannelType;
  title: string;
  description: string;
  identityHint: string;
  mode: string;
}> = [
  {
    type: "telegram_personal",
    title: "Telegram personal account",
    description: "Connect an explicitly authorized account for direct-message replies.",
    identityHint: "telegram:your-account-id",
    mode: "QR or OTP connector (provider-owned flow)",
  },
  {
    type: "whatsapp_business",
    title: "WhatsApp Business",
    description: "Use the official WhatsApp Business API; personal WhatsApp credentials are not accepted.",
    identityHint: "business:your-phone-number-id",
    mode: "Meta Business authorization",
  },
  {
    type: "facebook_page",
    title: "Facebook Messenger Page",
    description: "Connect a Page you own so messages stay within the approved Page scope.",
    identityHint: "page:your-page-id",
    mode: "Meta Page authorization",
  },
  {
    type: "email",
    title: "Email inbox",
    description: "Reserve an inbox for support replies with a tenant-owned identity.",
    identityHint: "support@example.com",
    mode: "Mailbox connector",
  },
];

const statusLabel: Record<ChannelStatus, string> = {
  pending: "Setup pending",
  connected: "Connected",
  paused: "Paused",
  revoked: "Revoked",
  error: "Needs attention",
};

function channelLabel(type: ChannelType): string {
  return channelOptions.find((item) => item.type === type)?.title ?? type;
}

export function ChannelSettings() {
  const [channels, setChannels] = useState<ChannelInstallationResponse[]>([]);
  const [bots, setBots] = useState<BotResponse[]>([]);
  const [selectedBotId, setSelectedBotId] = useState("");
  const [selectedType, setSelectedType] = useState<ChannelType>("telegram_personal");
  const [identity, setIdentity] = useState("");
  const [scope, setScope] = useState("");
  const [consent, setConsent] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const selected = useMemo(
    () => channelOptions.find((option) => option.type === selectedType) ?? channelOptions[0],
    [selectedType],
  );
  const activeBots = useMemo(() => bots.filter((bot) => bot.status === "active"), [bots]);

  async function refresh() {
    try {
      setError(null);
      const [nextChannels, nextBots] = await Promise.all([
        dashboardApi.listChannels(),
        dashboardApi.listBots(),
      ]);
      setChannels(nextChannels);
      setBots(nextBots);
      setSelectedBotId((current) => current || nextBots.find((bot) => bot.status === "active")?.id || "");
    } catch (cause) {
      setError(cause instanceof DashboardApiError ? cause.message : "Channels could not be loaded.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void refresh(); }, []);

  async function install(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      if (!selectedBotId) {
        setError("Create or activate a bot before installing a channel.");
        return;
      }
      const created = await dashboardApi.installChannel({
        channel_type: selectedType,
        bot_id: selectedBotId,
        external_identity: identity,
        conversation_scope: scope.split(",").map((item) => item.trim()).filter(Boolean),
        consent_acknowledged: consent,
      });
      setChannels((current) => [created, ...current]);
      setIdentity("");
      setScope("");
      setConsent(false);
      setNotice("Installation recorded. Complete the provider-owned authorization flow to connect it.");
    } catch (cause) {
      setError(cause instanceof DashboardApiError ? cause.message : "The channel could not be installed.");
    } finally {
      setSaving(false);
    }
  }

  async function setStatus(channel: ChannelInstallationResponse, status: ChannelStatus) {
    try {
      const updated = await dashboardApi.updateChannel(channel.id, { status });
      setChannels((current) => current.map((item) => item.id === updated.id ? updated : item));
    } catch (cause) {
      setError(cause instanceof DashboardApiError ? cause.message : "The channel status could not be updated.");
    }
  }

  async function assignBot(channel: ChannelInstallationResponse, botId: string) {
    try {
      const updated = await dashboardApi.updateChannel(channel.id, { bot_id: botId });
      setChannels((current) => current.map((item) => item.id === updated.id ? updated : item));
    } catch (cause) {
      setError(cause instanceof DashboardApiError ? cause.message : "The assigned bot could not be updated.");
    }
  }

  async function revoke(channel: ChannelInstallationResponse) {
    if (!window.confirm(`Revoke ${channelLabel(channel.channel_type)}?`)) return;
    try {
      await dashboardApi.revokeChannel(channel.id);
      setChannels((current) => current.map((item) => item.id === channel.id ? { ...item, status: "revoked" } : item));
    } catch (cause) {
      setError(cause instanceof DashboardApiError ? cause.message : "The channel could not be revoked.");
    }
  }

  return (
    <div className="dashboard-page channel-page">
      <section className="page-hero">
        <span className="eyebrow"><span className="eyebrow-pulse" />Channel connections</span>
        <h1>Meet customers where they already are.</h1>
        <p>Each channel is tenant-scoped and uses its approved connection mode. QR/OTP values and access tokens stay inside provider-owned authorization screens.</p>
      </section>
      {error ? <div className="form-alert"><span className="form-alert-mark">!</span><span>{error}</span></div> : null}
      {notice ? <div className="success-banner" role="status">{notice}</div> : null}
      <div className="channel-layout">
        <section className="config-card">
          <div className="config-card-heading"><div><span className="eyebrow">Add a channel</span><h2>Approved connection modes</h2></div><MessageIcon width={22} height={22} /></div>
          <form className="workspace-form channel-form" onSubmit={install}>
            <div className="channel-options" role="radiogroup" aria-label="Channel type">
              {channelOptions.map((option) => (
                <label className={`channel-option ${selectedType === option.type ? "channel-option-active" : ""}`} key={option.type}>
                  <input type="radio" name="channel-type" value={option.type} checked={selectedType === option.type} onChange={() => setSelectedType(option.type)} />
                  <span><strong>{option.title}</strong><small>{option.description}</small><em>{option.mode}</em></span>
                </label>
              ))}
            </div>
            <div className="field">
              <label htmlFor="channel-bot">Bot allowed to answer</label>
              <select id="channel-bot" required value={selectedBotId} onChange={(event) => setSelectedBotId(event.target.value)}>
                <option value="">Choose an active bot</option>
                {activeBots.map((bot) => <option key={bot.id} value={bot.id}>{bot.name}</option>)}
              </select>
              <span className="field-hint">Only the selected bot may answer conversations received through this channel.</span>
            </div>
            {activeBots.length === 0 ? <div className="workspace-alert">No active bot is available. <Link href="/dashboard/bots">Create or activate a bot first.</Link></div> : null}
            <div className="field"><label htmlFor="channel-identity">Account or page identity</label><input id="channel-identity" required value={identity} onChange={(event) => setIdentity(event.target.value)} placeholder={selected.identityHint} /><span className="field-hint">Use the prefix shown in the placeholder. Secrets, OTPs, and access tokens are never entered here.</span></div>
            <div className="field"><label htmlFor="channel-scope">Conversation scope (optional)</label><input id="channel-scope" value={scope} onChange={(event) => setScope(event.target.value)} placeholder="dm:123, page-inbox:456" /><span className="field-hint">Comma-separated IDs limit what the connector may read and reply to.</span></div>
            <label className="consent-check"><input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} required /><span>I authorize this tenant to read and reply within the selected account/page and scope.</span></label>
            <button className="button button-primary" type="submit" disabled={saving || activeBots.length === 0}>{saving ? "Saving…" : <><PlusIcon width={16} height={16} />Start secure setup</>}</button>
          </form>
        </section>
        <aside className="config-card channel-safety-card"><div className="config-card-heading"><div><span className="eyebrow">Safety boundary</span><h2>Connector handoff</h2></div><ArrowIcon width={22} height={22} /></div><div className="channel-safety-copy"><p>Telegram personal accounts may show a QR/OTP step in the connector. WhatsApp requires Business API access. Facebook requires a tenant-owned Page.</p><p>This screen stores only status, identity, scope, consent, and an opaque provider reference.</p></div></aside>
      </div>
      <section className="config-card"><div className="config-card-heading"><div><span className="eyebrow">Your workspace</span><h2>Installed channels</h2></div><span className="channel-count">{channels.length} total</span></div>{loading ? <div className="provider-list-skeleton skeleton" /> : channels.length === 0 ? <div className="empty-state"><strong>No channels connected yet.</strong><span>Start a secure setup above to add your first customer inbox.</span></div> : <div className="channel-list">{channels.map((channel) => <div className="channel-row" key={channel.id}><div><strong>{channelLabel(channel.channel_type)}</strong><span>{channel.external_identity}</span><small>{channel.conversation_scope.length ? `${channel.conversation_scope.length} scoped conversation(s)` : "All approved conversations"}</small>{channel.status === "pending" ? <small>Waiting for the provider authorization flow to confirm this connection.</small> : null}<label className="channel-bot-select"><span>Assigned bot</span><select value={channel.bot_id ?? ""} onChange={(event) => void assignBot(channel, event.target.value)} disabled={channel.status === "revoked"}><option value="" disabled>Choose a bot</option>{activeBots.map((bot) => <option key={bot.id} value={bot.id}>{bot.name}</option>)}</select></label></div><div className="channel-row-actions"><span className={`status-badge status-${channel.status}`}>{statusLabel[channel.status]}</span>{channel.status === "connected" ? <button className="button button-small" type="button" onClick={() => void setStatus(channel, "paused")}>Pause</button> : null}{channel.status !== "revoked" ? <button className="button button-small button-danger" type="button" onClick={() => void revoke(channel)}>Revoke</button> : null}</div></div>)}</div>}</section>
    </div>
  );
}
