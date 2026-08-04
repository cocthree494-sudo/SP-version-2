"use client";

import type { BotResponse, BotStatus } from "@support-agent/api-client";
import Link from "next/link";
import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { BotIcon, EditIcon, PlusIcon, TrashIcon } from "@/components/icons";
import { useAuth } from "@/lib/auth-context";
import { dashboardApi } from "@/lib/dashboard-api";

interface BotDraft {
  name: string;
  defaultLanguage: string;
  status: BotStatus;
  systemPolicy: string;
}

const EMPTY_DRAFT: BotDraft = {
  name: "",
  defaultLanguage: "auto",
  status: "active",
  systemPolicy: "",
};

export function BotManagement() {
  const { user } = useAuth();
  const canManage = user?.role === "owner" || user?.role === "admin";
  const [bots, setBots] = useState<BotResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<BotResponse | null>(null);
  const [draft, setDraft] = useState<BotDraft>(EMPTY_DRAFT);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState<BotResponse | null>(null);
  const botNameRef = useRef<HTMLInputElement>(null);
  const keepBotRef = useRef<HTMLButtonElement>(null);

  const loadBots = useCallback(async () => {
    try {
      setError(null);
      setBots(await dashboardApi.listBots());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Bots could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadBots();
  }, [loadBots]);

  useEffect(() => {
    if (editorOpen) botNameRef.current?.focus();
  }, [editorOpen]);

  useEffect(() => {
    if (deleting) keepBotRef.current?.focus();
  }, [deleting]);

  useEffect(() => {
    if (!editorOpen && !deleting) return;
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key !== "Escape" || saving) return;
      if (deleting) setDeleting(null);
      else setEditorOpen(false);
    }
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [deleting, editorOpen, saving]);

  function openCreate() {
    setEditing(null);
    setDraft(EMPTY_DRAFT);
    setEditorOpen(true);
    setNotice(null);
  }

  function openEdit(bot: BotResponse) {
    setEditing(bot);
    setDraft({
      name: bot.name,
      defaultLanguage: bot.default_language,
      status: bot.status,
      systemPolicy: bot.system_policy ?? "",
    });
    setEditorOpen(true);
    setNotice(null);
  }

  async function saveBot(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const payload = {
        name: draft.name.trim(),
        default_language: draft.defaultLanguage.trim().toLowerCase(),
        status: draft.status,
        system_policy: draft.systemPolicy.trim() || null,
      };
      const saved = editing
        ? await dashboardApi.updateBot(editing.id, payload)
        : await dashboardApi.createBot(payload);
      setBots((current) =>
        editing
          ? current.map((bot) => (bot.id === saved.id ? saved : bot))
          : [...current, saved],
      );
      setEditorOpen(false);
      setNotice(editing ? `${saved.name} was updated.` : `${saved.name} is ready to build.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The bot could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  async function confirmDelete() {
    if (!deleting) return;
    const target = deleting;
    setSaving(true);
    setError(null);
    try {
      await dashboardApi.deleteBot(target.id);
      setBots((current) => current.filter((bot) => bot.id !== target.id));
      setDeleting(null);
      setNotice(`${target.name} was deleted.`);
    } catch (caught) {
      setDeleting(null);
      setError(caught instanceof Error ? caught.message : "The bot could not be deleted.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="workspace-screen">
      <header className="screen-heading">
        <div>
          <span className="eyebrow">Agent studio</span>
          <h1>Build the voice behind your support.</h1>
          <p>Create focused bots, tune their policy, and pause them without losing knowledge.</p>
        </div>
        {canManage ? (
          <button className="button button-dark" type="button" onClick={openCreate}>
            <PlusIcon width={17} height={17} /> New bot
          </button>
        ) : null}
      </header>

      {error ? <div className="workspace-alert workspace-alert-error" role="alert">{error}</div> : null}
      {notice ? <div className="workspace-alert workspace-alert-success" role="status">{notice}</div> : null}
      {!canManage ? (
        <div className="workspace-alert">Your member role can view bots. An owner or admin manages changes.</div>
      ) : null}

      {loading ? (
        <div className="management-grid" aria-busy="true">
          <div className="skeleton management-skeleton" />
          <div className="skeleton management-skeleton" />
        </div>
      ) : bots.length === 0 ? (
        <section className="empty-workspace" aria-labelledby="empty-bots-title">
          <span className="empty-icon"><BotIcon width={26} height={26} /></span>
          <h2 id="empty-bots-title">Your first bot starts with a point of view.</h2>
          <p>Name it, choose its language behavior, and add the boundaries it should follow.</p>
          {canManage ? <button className="button button-primary" type="button" onClick={openCreate}>Create a bot</button> : null}
        </section>
      ) : (
        <section className="management-grid" aria-label="Bots">
          {bots.map((bot) => (
            <article className="management-card" key={bot.id}>
              <div className="management-card-top">
                <span className="management-icon"><BotIcon width={21} height={21} /></span>
                <span className={`state-badge state-${bot.status}`}><span />{bot.status}</span>
              </div>
              <h2>{bot.name}</h2>
              <p>{bot.system_policy || "Uses the grounded support policy without extra instructions."}</p>
              <dl className="compact-details">
                <div><dt>Language</dt><dd>{bot.default_language === "auto" ? "Match customer" : bot.default_language}</dd></div>
                <div><dt>Updated</dt><dd>{new Date(bot.updated_at).toLocaleDateString()}</dd></div>
              </dl>
              {canManage ? (
                <div className="card-actions">
                  <button className="button button-quiet" type="button" onClick={() => openEdit(bot)}><EditIcon width={15} height={15} /> Edit</button>
                  <Link className="button button-quiet" href={`/dashboard/knowledge?bot=${encodeURIComponent(bot.id)}`}>Knowledge</Link>
                  <button className="icon-action icon-action-danger" type="button" aria-label={`Delete ${bot.name}`} onClick={() => setDeleting(bot)}><TrashIcon width={16} height={16} /></button>
                </div>
              ) : null}
            </article>
          ))}
        </section>
      )}

      {editorOpen ? (
        <div className="dialog-backdrop" role="presentation">
          <section className="workspace-dialog" role="dialog" aria-modal="true" aria-labelledby="bot-dialog-title">
            <div className="dialog-heading">
              <div><span className="eyebrow">{editing ? "Tune agent" : "New agent"}</span><h2 id="bot-dialog-title">{editing ? `Edit ${editing.name}` : "Create a support bot"}</h2></div>
              <button className="dialog-close" type="button" aria-label="Close bot editor" onClick={() => setEditorOpen(false)} disabled={saving}>×</button>
            </div>
            <form className="workspace-form" onSubmit={saveBot}>
              <label>Bot name<input ref={botNameRef} value={draft.name} onChange={(event) => setDraft({...draft, name: event.target.value})} required maxLength={200} placeholder="Northstar Guide" /></label>
              <div className="form-row">
                <label>Default language<input value={draft.defaultLanguage} onChange={(event) => setDraft({...draft, defaultLanguage: event.target.value})} required pattern="auto|[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*" title="Use auto or a language tag such as en or bn-BD" placeholder="auto or en" /></label>
                <label>Status<select value={draft.status} onChange={(event) => setDraft({...draft, status: event.target.value as BotStatus})}><option value="active">Active</option><option value="disabled">Disabled</option></select></label>
              </div>
              <label>Support policy<textarea value={draft.systemPolicy} onChange={(event) => setDraft({...draft, systemPolicy: event.target.value})} maxLength={20000} rows={6} placeholder="Optional tone, escalation, and policy boundaries…" /></label>
              <p className="form-note">Retrieved knowledge remains untrusted data; this policy stays in the trusted instruction boundary.</p>
              <div className="dialog-actions"><button className="button button-quiet" type="button" onClick={() => setEditorOpen(false)} disabled={saving}>Cancel</button><button className="button button-primary" type="submit" disabled={saving}>{saving ? "Saving…" : editing ? "Save changes" : "Create bot"}</button></div>
            </form>
          </section>
        </div>
      ) : null}

      {deleting ? (
        <div className="dialog-backdrop" role="presentation">
          <section className="workspace-dialog workspace-dialog-small" role="alertdialog" aria-modal="true" aria-labelledby="delete-bot-title" aria-describedby="delete-bot-copy">
            <span className="danger-icon"><TrashIcon width={21} height={21} /></span>
            <h2 id="delete-bot-title">Delete {deleting.name}?</h2>
            <p id="delete-bot-copy">This removes the bot and its connected credentials and knowledge. This action cannot be undone.</p>
            <div className="dialog-actions"><button ref={keepBotRef} className="button button-quiet" type="button" onClick={() => setDeleting(null)} disabled={saving}>Keep bot</button><button className="button button-danger" type="button" disabled={saving} onClick={() => void confirmDelete()}>{saving ? "Deleting…" : "Delete bot"}</button></div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
