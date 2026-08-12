"use client";

import { useEffect, useState } from "react";

import type { VoiceAgentResponse, VoiceStatus } from "@support-agent/api-client";

import { ArrowIcon, PhoneIcon } from "@/components/icons";
import { DashboardApiError, dashboardApi } from "@/lib/dashboard-api";

const statusLabel: Record<VoiceStatus, string> = {
  pending: "Provider verification pending",
  ready: "Ready",
  paused: "Paused",
  error: "Needs attention",
};

export function VoiceSettings() {
  const [agents, setAgents] = useState<VoiceAgentResponse[]>([]);
  const [provider, setProvider] = useState<"twilio" | "sip">("twilio");
  const [phone, setPhone] = useState("");
  const [language, setLanguage] = useState("auto");
  const [voice, setVoice] = useState("alloy");
  const [limit, setLimit] = useState("100");
  const [outbound, setOutbound] = useState(false);
  const [recording, setRecording] = useState(false);
  const [consent, setConsent] = useState(false);
  const [outboundConsent, setOutboundConsent] = useState(false);
  const [recordingConsent, setRecordingConsent] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    dashboardApi.listVoiceAgents().then(setAgents).catch((cause) => {
      setError(cause instanceof DashboardApiError ? cause.message : "Voice agents could not be loaded.");
    }).finally(() => setLoading(false));
  }, []);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const created = await dashboardApi.installVoiceAgent({
        provider,
        phone_number: phone,
        language,
        voice,
        monthly_cost_limit_usd: Number(limit),
        outbound_enabled: outbound,
        recording_enabled: recording,
        retention_days: recording ? 30 : 0,
        consent_acknowledged: consent,
        outbound_consent: outboundConsent,
        recording_consent: recordingConsent,
      });
      setAgents((current) => [created, ...current]);
      setPhone("");
      setConsent(false);
      setNotice("Voice setup saved. Connect and verify the telephony provider before taking live calls.");
    } catch (cause) {
      setError(cause instanceof DashboardApiError ? cause.message : "Voice setup could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  async function setStatus(agent: VoiceAgentResponse, status: VoiceStatus) {
    try {
      const updated = await dashboardApi.updateVoiceAgent(agent.id, status);
      setAgents((current) => current.map((item) => item.id === updated.id ? updated : item));
    } catch (cause) {
      setError(cause instanceof DashboardApiError ? cause.message : "Voice status could not be updated.");
    }
  }

  return (
    <div className="dashboard-page voice-page">
      <section className="page-hero"><span className="eyebrow"><span className="eyebrow-pulse" />Voice call agent</span><h1>Let support speak with care.</h1><p>Voice reuses the same tenant agent core for speech-to-text, grounded responses, interruption handling, and text-to-speech. Live calls stay locked until an approved telephony provider is verified.</p></section>
      {error ? <div className="form-alert"><span className="form-alert-mark">!</span><span>{error}</span></div> : null}
      {notice ? <div className="success-banner" role="status">{notice}</div> : null}
      <div className="voice-layout">
        <section className="config-card"><div className="config-card-heading"><div><span className="eyebrow">Secure setup</span><h2>Configure your call agent</h2></div><PhoneIcon width={22} height={22} /></div><form className="workspace-form voice-form" onSubmit={submit}><div className="form-row"><div className="field"><label htmlFor="voice-provider">Telephony mode</label><select id="voice-provider" value={provider} onChange={(event) => setProvider(event.target.value as "twilio" | "sip")}><option value="twilio">Twilio (approved adapter)</option><option value="sip">SIP trunk (approved adapter)</option></select></div><div className="field"><label htmlFor="voice-number">Business phone number</label><input id="voice-number" required value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="+1 555 0100" /></div></div><div className="form-row"><div className="field"><label htmlFor="voice-language">Language</label><select id="voice-language" value={language} onChange={(event) => setLanguage(event.target.value)}><option value="auto">Auto detect</option><option value="en">English</option><option value="bn">বাংলা</option></select></div><div className="field"><label htmlFor="voice-name">Voice</label><select id="voice-name" value={voice} onChange={(event) => setVoice(event.target.value)}><option value="alloy">Alloy</option><option value="verse">Verse</option><option value="aria">Aria</option></select></div></div><div className="field"><label htmlFor="voice-limit">Monthly cost limit (USD)</label><input id="voice-limit" type="number" min="1" max="100000" value={limit} onChange={(event) => setLimit(event.target.value)} /><span className="field-hint">Calls stop at this tenant-level budget until an admin raises it.</span></div><div className="voice-toggles"><label className="consent-check"><input type="checkbox" checked={outbound} onChange={(event) => setOutbound(event.target.checked)} /><span>Allow outbound calls</span></label>{outbound ? <label className="consent-check nested"><input type="checkbox" checked={outboundConsent} onChange={(event) => setOutboundConsent(event.target.checked)} required /><span>I have consent for outbound calling in my region.</span></label> : null}<label className="consent-check"><input type="checkbox" checked={recording} onChange={(event) => setRecording(event.target.checked)} /><span>Record calls for quality review</span></label>{recording ? <label className="consent-check nested"><input type="checkbox" checked={recordingConsent} onChange={(event) => setRecordingConsent(event.target.checked)} required /><span>I have informed callers and have recording consent.</span></label> : null}</div><label className="consent-check"><input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} required /><span>I authorize this tenant to process voice audio for support, subject to the selected controls.</span></label><button className="button button-primary" type="submit" disabled={saving}>{saving ? "Saving…" : "Save voice setup"}</button></form></section>
        <aside className="config-card channel-safety-card"><div className="config-card-heading"><div><span className="eyebrow">Live-call gate</span><h2>Provider verification</h2></div><ArrowIcon width={22} height={22} /></div><div className="channel-safety-copy"><p>Audio is not stored by this setup screen. Recording is off by default and retention is zero until explicitly enabled.</p><p>Webhook signatures, call-cost limits, caller consent, silence timeouts, and interruption events are required before production activation.</p></div></aside>
      </div>
      <section className="config-card"><div className="config-card-heading"><div><span className="eyebrow">Your workspace</span><h2>Voice agents</h2></div><span className="channel-count">{agents.length} total</span></div>{loading ? <div className="provider-list-skeleton skeleton" /> : agents.length === 0 ? <div className="empty-state"><strong>No voice agent configured.</strong><span>Add a number above, then complete provider verification.</span></div> : <div className="channel-list">{agents.map((agent) => <div className="channel-row" key={agent.id}><div><strong>{agent.phone_number}</strong><span>{agent.provider} · {agent.language} · {agent.voice}</span><small>Monthly cap ${agent.monthly_cost_limit_usd} · recording {agent.recording_enabled ? "on" : "off"}</small></div><div className="channel-row-actions"><span className={`status-badge status-${agent.status}`}>{statusLabel[agent.status]}</span>{agent.status === "pending" ? <button className="button button-small button-dark" type="button" onClick={() => void setStatus(agent, "ready")}>Mark verified</button> : null}{agent.status === "ready" ? <button className="button button-small" type="button" onClick={() => void setStatus(agent, "paused")}>Pause</button> : null}</div></div>)}</div>}</section>
    </div>
  );
}
