"use client";

import type { BotKeyResponse, BotResponse } from "@support-agent/api-client";
import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { GlobeIcon, MessageIcon, PlusIcon, TrashIcon } from "@/components/icons";
import { useAuth } from "@/lib/auth-context";
import { dashboardApi } from "@/lib/dashboard-api";

const PUBLIC_API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
const WIDGET_LOADER_URL =
  process.env.NEXT_PUBLIC_WIDGET_LOADER_URL ?? "http://127.0.0.1:5173/loader.js";

function splitOrigins(value: string): string[] {
  return [...new Set(value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean))];
}

function htmlAttribute(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function buildSnippet(bot: BotResponse, key: BotKeyResponse): string {
  return `<script
  async
  src="${htmlAttribute(WIDGET_LOADER_URL)}"
  data-api-base="${htmlAttribute(PUBLIC_API_URL)}"
  data-publishable-key="${htmlAttribute(key.publishable_key)}"
  data-title="${htmlAttribute(bot.name)}"
  data-welcome="${htmlAttribute(bot.widget_welcome_text)}"
  data-accent="${htmlAttribute(bot.widget_accent_color)}"
  data-position="${bot.widget_position}"
></script>`;
}

export function WidgetConfiguration() {
  const { user } = useAuth();
  const canManage = user?.role === "owner" || user?.role === "admin";
  const [bots, setBots] = useState<BotResponse[]>([]);
  const [selectedBotId, setSelectedBotId] = useState("");
  const [keys, setKeys] = useState<BotKeyResponse[]>([]);
  const [selectedKeyId, setSelectedKeyId] = useState("");
  const [welcome, setWelcome] = useState("How can we help?");
  const [accent, setAccent] = useState("#194f46");
  const [position, setPosition] = useState<"left" | "right">("right");
  const [label, setLabel] = useState("Website");
  const [origins, setOrigins] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [revoking, setRevoking] = useState<BotKeyResponse | null>(null);
  const keepKeyRef = useRef<HTMLButtonElement>(null);

  const activeBot = useMemo(
    () => bots.find((bot) => bot.id === selectedBotId) ?? null,
    [bots, selectedBotId],
  );
  const activeKeys = useMemo(() => keys.filter((key) => key.revoked_at === null), [keys]);
  const selectedKey = useMemo(
    () => activeKeys.find((key) => key.id === selectedKeyId) ?? activeKeys[0] ?? null,
    [activeKeys, selectedKeyId],
  );
  const snippet = activeBot && selectedKey ? buildSnippet(activeBot, selectedKey) : "";

  useEffect(() => {
    let cancelled = false;
    dashboardApi
      .listBots()
      .then((items) => {
        if (cancelled) return;
        setBots(items);
        setSelectedBotId(items[0]?.id ?? "");
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(caught instanceof Error ? caught.message : "Bots could not be loaded.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    setOrigins(window.location.origin);
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!activeBot) {
      setKeys([]);
      return;
    }
    setWelcome(activeBot.widget_welcome_text);
    setAccent(activeBot.widget_accent_color);
    setPosition(activeBot.widget_position);
    setError(null);
    dashboardApi
      .listBotKeys(activeBot.id)
      .then((items) => {
        setKeys(items);
        const firstActive = items.find((key) => key.revoked_at === null);
        setSelectedKeyId(firstActive?.id ?? "");
        if (firstActive) setOrigins(firstActive.allowed_origins.join("\n"));
      })
      .catch((caught: unknown) => {
        setError(caught instanceof Error ? caught.message : "Widget keys could not be loaded.");
      });
  }, [activeBot]);

  useEffect(() => {
    if (selectedKey) setOrigins(selectedKey.allowed_origins.join("\n"));
  }, [selectedKey]);

  useEffect(() => {
    if (revoking) keepKeyRef.current?.focus();
  }, [revoking]);

  async function saveAppearance(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!activeBot || !canManage) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await dashboardApi.updateBot(activeBot.id, {
        widget_welcome_text: welcome.trim(),
        widget_accent_color: accent,
        widget_position: position,
      });
      setBots((current) => current.map((bot) => bot.id === updated.id ? updated : bot));
      setNotice("Widget appearance saved.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Appearance could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  async function createKey(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!activeBot || !canManage) return;
    const allowedOrigins = splitOrigins(origins);
    if (!allowedOrigins.length) {
      setError("Add at least one exact website origin.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const created = await dashboardApi.createBotKey(activeBot.id, {
        label: label.trim() || "Website",
        allowed_origins: allowedOrigins,
      });
      setKeys((current) => [...current, created]);
      setSelectedKeyId(created.id);
      setNotice("Publishable widget key created.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Widget key could not be created.");
    } finally {
      setBusy(false);
    }
  }

  async function updateOrigins() {
    if (!activeBot || !selectedKey || !canManage) return;
    const allowedOrigins = splitOrigins(origins);
    if (!allowedOrigins.length) {
      setError("Add at least one exact website origin.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const updated = await dashboardApi.updateBotKey(activeBot.id, selectedKey.id, {
        allowed_origins: allowedOrigins,
      });
      setKeys((current) => current.map((key) => key.id === updated.id ? updated : key));
      setNotice("Allowed origins updated immediately.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Origins could not be updated.");
    } finally {
      setBusy(false);
    }
  }

  async function confirmRevoke() {
    if (!activeBot || !revoking || !canManage) return;
    const target = revoking;
    setBusy(true);
    setError(null);
    try {
      await dashboardApi.revokeBotKey(activeBot.id, target.id);
      setKeys((current) => current.map((key) =>
        key.id === target.id ? { ...key, revoked_at: new Date().toISOString() } : key,
      ));
      setRevoking(null);
      setSelectedKeyId("");
      setNotice("Key revoked. Existing widget sessions are now invalid.");
    } catch (caught) {
      setRevoking(null);
      setError(caught instanceof Error ? caught.message : "Widget key could not be revoked.");
    } finally {
      setBusy(false);
    }
  }

  async function copySnippet() {
    try {
      await navigator.clipboard.writeText(snippet);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setError("Copy was blocked. Select the snippet and copy it manually.");
    }
  }

  return (
    <div className="workspace-screen widget-config-screen">
      <header className="screen-heading screen-heading-compact">
        <div><span className="eyebrow">Web channel</span><h1>Make support feel at home.</h1><p>Style the launcher, allow exact website origins, and copy one installation snippet.</p></div>
        <label className="bot-picker">Bot<select value={selectedBotId} onChange={(event) => setSelectedBotId(event.target.value)} disabled={loading}>{bots.map((bot) => <option key={bot.id} value={bot.id}>{bot.name}</option>)}</select></label>
      </header>

      {error ? <div className="workspace-alert workspace-alert-error" role="alert">{error}</div> : null}
      {notice ? <div className="workspace-alert workspace-alert-success" role="status">{notice}</div> : null}
      {!canManage ? <div className="workspace-alert">You can inspect widget settings. An owner or admin manages changes.</div> : null}

      {!loading && !activeBot ? (
        <section className="empty-workspace"><span className="empty-icon"><MessageIcon width={26} height={26}/></span><h2>Create a bot before configuring its widget.</h2></section>
      ) : activeBot ? (
        <div className="widget-config-layout">
          <div className="widget-config-stack">
            <section className="config-card">
              <div className="config-card-heading"><div><span className="eyebrow">Appearance</span><h2>Theme and greeting</h2></div></div>
              <form className="workspace-form" onSubmit={saveAppearance}>
                <label>Welcome text<input value={welcome} onChange={(event) => setWelcome(event.target.value)} minLength={1} maxLength={160} required disabled={!canManage}/></label>
                <div className="form-row">
                  <label>Accent color<span className="color-input"><input type="color" value={accent} onChange={(event) => setAccent(event.target.value)}/><input value={accent} onChange={(event) => setAccent(event.target.value)} pattern="#[0-9a-fA-F]{6}" maxLength={7} disabled={!canManage}/></span></label>
                  <label>Launcher position<select value={position} onChange={(event) => setPosition(event.target.value as "left" | "right")} disabled={!canManage}><option value="right">Bottom right</option><option value="left">Bottom left</option></select></label>
                </div>
                {canManage ? <div className="builder-submit"><button className="button button-primary" disabled={busy}>Save appearance</button></div> : null}
              </form>
            </section>

            <section className="config-card">
              <div className="config-card-heading"><div><span className="eyebrow">Security boundary</span><h2>Key and allowed origins</h2></div></div>
              {activeKeys.length ? (
                <div className="key-manager">
                  <label>Active key<select value={selectedKey?.id ?? ""} onChange={(event) => setSelectedKeyId(event.target.value)}>{activeKeys.map((key) => <option value={key.id} key={key.id}>{key.label} · {key.publishable_key.slice(-8)}</option>)}</select></label>
                  <label>Exact origins<textarea rows={4} value={origins} onChange={(event) => setOrigins(event.target.value)} disabled={!canManage} placeholder="https://www.example.com"/><small>One origin per line. Paths and wildcards are rejected.</small></label>
                  {canManage ? <div className="key-actions"><button className="button button-quiet" type="button" onClick={() => void updateOrigins()} disabled={busy}>Save origins</button><button className="button button-danger" type="button" onClick={() => setRevoking(selectedKey)} disabled={busy || !selectedKey}><TrashIcon width={14} height={14}/> Revoke key</button></div> : null}
                </div>
              ) : (
                <form className="workspace-form" onSubmit={createKey}>
                  <label>Key label<input value={label} onChange={(event) => setLabel(event.target.value)} maxLength={100} required disabled={!canManage}/></label>
                  <label>Exact origins<textarea rows={4} value={origins} onChange={(event) => setOrigins(event.target.value)} required disabled={!canManage} placeholder="https://www.example.com"/><small>Use the browser origin only—scheme, host, and optional port.</small></label>
                  {canManage ? <div className="builder-submit"><button className="button button-primary" disabled={busy}><PlusIcon width={15} height={15}/> Create widget key</button></div> : null}
                </form>
              )}
            </section>

            <section className="config-card install-card">
              <div className="config-card-heading"><div><span className="eyebrow">Install</span><h2>Paste before &lt;/body&gt;</h2></div>{snippet ? <button className="button button-dark" type="button" onClick={() => void copySnippet()}>{copied ? "Copied" : "Copy snippet"}</button> : null}</div>
              {snippet ? <pre tabIndex={0}><code>{snippet}</code></pre> : <div className="source-empty"><p>Create an active widget key to generate the snippet.</p></div>}
              <ol className="install-steps"><li>Copy the script into every page that needs support.</li><li>Add each production/staging site as an exact allowed origin.</li><li>Publish, open the site, and send a grounded test question.</li></ol>
            </section>
          </div>

          <aside className="widget-preview-card">
            <div className="preview-browser"><div className="preview-browser-bar"><i/><i/><i/><span>your website</span></div><div className="preview-page"><div className="preview-lines"><i/><i/><i/></div><div className={`preview-widget preview-widget-${position}`} style={{ "--preview-accent": accent } as React.CSSProperties}><div className="preview-panel"><header><strong>{activeBot.name}</strong><span>Typically replies in moments</span></header><main><span className="preview-bubble">{welcome}</span></main><footer>Type your question…</footer></div><span className="preview-launcher"><MessageIcon width={20} height={20}/></span></div></div></div>
            <div className="preview-note"><GlobeIcon width={16} height={16}/><span><strong>Isolated by Shadow DOM</strong>Host-page CSS cannot restyle this previewed widget.</span></div>
          </aside>
        </div>
      ) : null}

      {revoking ? <div className="dialog-backdrop" role="presentation"><section className="workspace-dialog workspace-dialog-small" role="alertdialog" aria-modal="true" aria-labelledby="revoke-key-title"><span className="danger-icon"><TrashIcon width={21} height={21}/></span><h2 id="revoke-key-title">Revoke {revoking.label}?</h2><p>Existing anonymous sessions using this key stop working immediately. Create a new key and update the embed snippet to restore access.</p><div className="dialog-actions"><button ref={keepKeyRef} className="button button-quiet" type="button" onClick={() => setRevoking(null)} disabled={busy}>Keep key</button><button className="button button-danger" type="button" onClick={() => void confirmRevoke()} disabled={busy}>{busy ? "Revoking…" : "Revoke key"}</button></div></section></div> : null}
    </div>
  );
}
