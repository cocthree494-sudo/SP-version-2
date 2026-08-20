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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    dashboardApi.listVoiceAgents().then(setAgents).catch((cause) => {
      setError(cause instanceof DashboardApiError ? cause.message : "Voice agents could not be loaded.");
    }).finally(() => setLoading(false));
  }, []);

  return (
    <div className="dashboard-page voice-page">
      <section className="page-hero"><span className="eyebrow"><span className="eyebrow-pulse" />Voice call agent</span><h1>Let support speak with care.</h1><p>Voice will reuse the same tenant agent core for speech-to-text, grounded responses, interruption handling, and text-to-speech.</p></section>
      <div className="form-alert" role="status"><span className="form-alert-mark">i</span><span><strong>Not available yet.</strong> No approved telephony adapter is implemented, so a configured number could never receive calls. Setup stays disabled until an adapter and its end-to-end call, consent, and abuse gates pass, rather than letting you save a number that would silently never answer.</span></div>
      {error ? <div className="form-alert"><span className="form-alert-mark">!</span><span>{error}</span></div> : null}
      <div className="voice-layout">
        <section className="config-card"><div className="config-card-heading"><div><span className="eyebrow">Planned setup</span><h2>Configure your call agent</h2></div><PhoneIcon width={22} height={22} /></div><div className="channel-safety-copy"><p>When voice opens, you will connect an approved telephony provider, assign one of your bots to a business number, and choose language and voice from an approved catalog.</p><p>Outbound calling, call recording, and transcript retention will each be separate opt-in capabilities with their own consent and regional policy controls. Recording will be off by default with zero retention.</p><p>Per-call and per-minute cost, provider latency, and a monthly spend cap will be visible before activation.</p></div></section>
        <aside className="config-card channel-safety-card"><div className="config-card-heading"><div><span className="eyebrow">Live-call gate</span><h2>Provider verification</h2></div><ArrowIcon width={22} height={22} /></div><div className="channel-safety-copy"><p>No audio is processed or stored today. Nothing on this page reaches a telephony provider.</p><p>Verified webhook signatures, call-cost limits, caller consent, silence timeouts, interruption handling, and a human handoff path are all required before production activation.</p></div></aside>
      </div>
      <section className="config-card"><div className="config-card-heading"><div><span className="eyebrow">Your workspace</span><h2>Voice agents</h2></div><span className="channel-count">{agents.length} total</span></div>{loading ? <div className="provider-list-skeleton skeleton" /> : agents.length === 0 ? <div className="empty-state"><strong>No voice agent configured.</strong><span>Voice setup opens once an approved telephony adapter is verified.</span></div> : <div className="channel-list">{agents.map((agent) => <div className="channel-row" key={agent.id}><div><strong>{agent.phone_number}</strong><span>{agent.provider} · {agent.language} · {agent.voice}</span><small>Monthly cap ${agent.monthly_cost_limit_usd} · recording {agent.recording_enabled ? "on" : "off"} · not connected to any provider</small></div><div className="channel-row-actions"><span className={`status-badge status-${agent.status}`}>{statusLabel[agent.status]}</span></div></div>)}</div>}</section>
    </div>
  );
}
