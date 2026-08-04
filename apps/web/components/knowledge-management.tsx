"use client";

import type {
  BotResponse,
  KnowledgeSourceResponse,
  KnowledgeSourceType,
} from "@support-agent/api-client";
import Link from "next/link";
import {
  type DragEvent,
  type FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  BookIcon,
  EditIcon,
  GlobeIcon,
  TrashIcon,
  UploadIcon,
} from "@/components/icons";
import { useAuth } from "@/lib/auth-context";
import { dashboardApi } from "@/lib/dashboard-api";

type SourceMode = "file" | "website" | "manual";

const SOURCE_MODES: SourceMode[] = ["file", "website", "manual"];
const PROCESSING_STATUSES = new Set(["pending", "processing", "deleting"]);

function formatFileSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function detailString(source: KnowledgeSourceResponse): string {
  if (source.type === "website") {
    return String(source.details.start_url ?? "Website crawl");
  }
  if (source.type === "manual") {
    return String(source.details.question ?? "Manual answer");
  }
  const size = formatFileSize(Number(source.details.size_bytes ?? 0));
  const filename = String(source.details.original_filename ?? source.name);
  return size ? `${filename} · ${size}` : filename;
}

function sourceIcon(type: KnowledgeSourceType) {
  if (type === "website") return <GlobeIcon width={19} height={19} />;
  if (type === "file") return <UploadIcon width={19} height={19} />;
  return <BookIcon width={19} height={19} />;
}

function upsertSource(
  sources: KnowledgeSourceResponse[],
  incoming: KnowledgeSourceResponse,
): KnowledgeSourceResponse[] {
  const index = sources.findIndex((source) => source.id === incoming.id);
  if (index === -1) return [...sources, incoming];
  return sources.map((source) => (source.id === incoming.id ? incoming : source));
}

export function KnowledgeManagement() {
  const { user } = useAuth();
  const canManage = user?.role === "owner" || user?.role === "admin";
  const [bots, setBots] = useState<BotResponse[]>([]);
  const [selectedBotId, setSelectedBotId] = useState("");
  const selectedBotIdRef = useRef("");
  const sourceRequestRef = useRef(0);
  const [sources, setSources] = useState<KnowledgeSourceResponse[]>([]);
  const [mode, setMode] = useState<SourceMode>("file");
  const [loading, setLoading] = useState(true);
  const [sourceLoading, setSourceLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [uploadLabel, setUploadLabel] = useState("");
  const [websiteName, setWebsiteName] = useState("");
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [maxPages, setMaxPages] = useState(20);
  const [maxDepth, setMaxDepth] = useState(2);
  const [manualName, setManualName] = useState("");
  const [manualQuestion, setManualQuestion] = useState("");
  const [manualAnswer, setManualAnswer] = useState("");
  const [editingManual, setEditingManual] = useState<KnowledgeSourceResponse | null>(null);
  const [deleting, setDeleting] = useState<KnowledgeSourceResponse | null>(null);
  const keepSourceRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let cancelled = false;
    dashboardApi
      .listBots()
      .then((items) => {
        if (cancelled) return;
        setBots(items);
        const requestedBotId = new URLSearchParams(window.location.search).get("bot");
        const requestedBot = items.find((item) => item.id === requestedBotId);
        setSelectedBotId((current) => current || requestedBot?.id || items[0]?.id || "");
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "Bots could not be loaded.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    selectedBotIdRef.current = selectedBotId;
  }, [selectedBotId]);

  useEffect(() => {
    if (deleting) keepSourceRef.current?.focus();
  }, [deleting]);

  useEffect(() => {
    if (!deleting) return;
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape" && !busy) setDeleting(null);
    }
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [busy, deleting]);

  const loadSources = useCallback(async (botId: string, showLoading = false) => {
    if (!botId) {
      setSources([]);
      return;
    }
    const requestId = ++sourceRequestRef.current;
    if (showLoading) setSourceLoading(true);
    try {
      const items = await dashboardApi.listSources(botId);
      if (selectedBotIdRef.current === botId && sourceRequestRef.current === requestId) {
        setSources(items);
        setError(null);
      }
    } catch (caught) {
      if (selectedBotIdRef.current === botId && sourceRequestRef.current === requestId) {
        setError(
          caught instanceof Error ? caught.message : "Knowledge sources could not be loaded.",
        );
      }
    } finally {
      if (showLoading && selectedBotIdRef.current === botId) setSourceLoading(false);
    }
  }, []);

  useEffect(() => {
    sourceRequestRef.current += 1;
    setSources([]);
    setEditingManual(null);
    setManualName("");
    setManualQuestion("");
    setManualAnswer("");
    if (selectedBotId) void loadSources(selectedBotId, true);
  }, [loadSources, selectedBotId]);

  const shouldPoll = sources.some((source) => PROCESSING_STATUSES.has(source.status));

  useEffect(() => {
    if (!selectedBotId || !shouldPoll) return;
    const timer = window.setInterval(() => void loadSources(selectedBotId), 4000);
    return () => window.clearInterval(timer);
  }, [loadSources, selectedBotId, shouldPoll]);

  const activeBot = useMemo(
    () => bots.find((bot) => bot.id === selectedBotId) ?? null,
    [bots, selectedBotId],
  );

  async function uploadFiles(files: FileList | File[]) {
    if (!selectedBotId || files.length === 0 || busy || !canManage) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    const inputFiles = Array.from(files);
    const failures: { name: string; message: string }[] = [];
    let uploaded = 0;
    try {
      for (const [index, file] of inputFiles.entries()) {
        setUploadLabel(`Uploading ${index + 1} of ${inputFiles.length}: ${file.name}`);
        try {
          const source = await dashboardApi.uploadFile(selectedBotId, file);
          uploaded += 1;
          setSources((current) => upsertSource(current, source));
        } catch (caught) {
          failures.push({
            name: file.name,
            message: caught instanceof Error ? caught.message : "Upload failed.",
          });
        }
      }
      if (uploaded > 0) {
        setNotice(`${uploaded} file${uploaded === 1 ? "" : "s"} queued for processing.`);
      }
      if (failures.length > 0) {
        const firstFailure = failures[0];
        setError(
          `${failures.length} file${failures.length === 1 ? "" : "s"} could not be uploaded. ` +
            `${firstFailure.name}: ${firstFailure.message}`,
        );
      }
    } finally {
      setBusy(false);
      setUploadLabel("");
    }
  }

  function acceptDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragging(false);
    if (!busy && canManage) void uploadFiles(event.dataTransfer.files);
  }

  async function createWebsite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedBotId || !canManage) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const source = await dashboardApi.createWebsite(selectedBotId, {
        url: websiteUrl,
        ...(websiteName.trim() ? { name: websiteName.trim() } : {}),
        max_pages: maxPages,
        max_depth: maxDepth,
      });
      setSources((current) => upsertSource(current, source));
      setWebsiteName("");
      setWebsiteUrl("");
      setNotice("Website crawl queued. Status will refresh automatically.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The website could not be added.");
    } finally {
      setBusy(false);
    }
  }

  function startManualEdit(source: KnowledgeSourceResponse) {
    setEditingManual(source);
    setManualName(source.name);
    setManualQuestion(String(source.details.question ?? ""));
    setManualAnswer(String(source.details.answer ?? ""));
    setMode("manual");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function clearManual() {
    setEditingManual(null);
    setManualName("");
    setManualQuestion("");
    setManualAnswer("");
  }

  async function saveManual(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedBotId || !canManage) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const payload = {
        question: manualQuestion,
        answer: manualAnswer,
        ...(manualName.trim() ? { name: manualName.trim() } : {}),
      };
      const source = editingManual
        ? await dashboardApi.updateManual(editingManual.id, payload)
        : await dashboardApi.createManual(selectedBotId, payload);
      setSources((current) => upsertSource(current, source));
      setNotice(
        editingManual
          ? "Manual answer updated and queued for re-embedding."
          : "Manual answer queued for processing.",
      );
      clearManual();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The manual answer could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  async function confirmDelete() {
    if (!deleting || !canManage) return;
    const target = deleting;
    setBusy(true);
    setError(null);
    try {
      await dashboardApi.deleteSource(target.id);
      setSources((current) => current.filter((source) => source.id !== target.id));
      setDeleting(null);
      setNotice(`${target.name} was removed.`);
    } catch (caught) {
      setDeleting(null);
      setError(caught instanceof Error ? caught.message : "The source could not be deleted.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="workspace-screen">
      <header className="screen-heading screen-heading-compact">
        <div>
          <span className="eyebrow">Knowledge studio</span>
          <h1>Give every answer a trusted source.</h1>
          <p>Upload documents, crawl a bounded website, or write an authoritative answer.</p>
        </div>
        {bots.length ? (
          <label className="bot-picker">
            Bot
            <select
              value={selectedBotId}
              onChange={(event) => setSelectedBotId(event.target.value)}
              disabled={busy}
            >
              {bots.map((bot) => (
                <option value={bot.id} key={bot.id}>{bot.name}</option>
              ))}
            </select>
          </label>
        ) : null}
      </header>

      {error ? <div className="workspace-alert workspace-alert-error" role="alert">{error}</div> : null}
      {notice ? <div className="workspace-alert workspace-alert-success" role="status">{notice}</div> : null}

      {loading ? (
        <div className="skeleton knowledge-skeleton" aria-label="Loading knowledge workspace" />
      ) : bots.length === 0 ? (
        <section className="empty-workspace" aria-labelledby="empty-knowledge-title">
          <span className="empty-icon"><BookIcon width={26} height={26} /></span>
          <h2 id="empty-knowledge-title">Create a bot before adding knowledge.</h2>
          <p>Knowledge is isolated per tenant and bot, so every source needs a destination.</p>
          {canManage ? <Link className="button button-primary" href="/dashboard/bots">Create a bot</Link> : null}
        </section>
      ) : (
        <>
          <section className="source-builder" aria-labelledby="source-builder-title">
            <div className="builder-intro">
              <div>
                <span className="eyebrow">Add to {activeBot?.name}</span>
                <h2 id="source-builder-title">Choose a source path.</h2>
              </div>
              <div className="source-tabs" aria-label="Knowledge source type">
                {SOURCE_MODES.map((item) => (
                  <button
                    className={mode === item ? "source-tab source-tab-active" : "source-tab"}
                    type="button"
                    aria-pressed={mode === item}
                    onClick={() => setMode(item)}
                    key={item}
                  >
                    {item}
                  </button>
                ))}
              </div>
            </div>

            {!canManage ? (
              <div className="workspace-alert">
                Your member role can view sources. An owner or admin adds or removes knowledge.
              </div>
            ) : null}

            {mode === "file" ? (
              <div className="builder-panel" aria-label="File source">
                <label
                  className={`file-dropzone ${dragging ? "file-dropzone-active" : ""} ${busy || !canManage ? "file-dropzone-disabled" : ""}`}
                  onDragOver={(event) => {
                    event.preventDefault();
                    if (!busy && canManage) setDragging(true);
                  }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={acceptDrop}
                >
                  <input
                    type="file"
                    multiple
                    accept=".pdf,.docx,.txt,.md,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,text/markdown"
                    disabled={busy || !canManage}
                    onChange={(event) => {
                      if (event.target.files) void uploadFiles(event.target.files);
                      event.target.value = "";
                    }}
                  />
                  <span className="drop-icon"><UploadIcon width={25} height={25} /></span>
                  <strong>{uploadLabel || "Drop files here, or choose from your device"}</strong>
                  <span>PDF, DOCX, TXT, or Markdown · up to the configured upload limit</span>
                </label>
              </div>
            ) : null}

            {mode === "website" ? (
              <form className="builder-panel workspace-form" aria-label="Website source" onSubmit={createWebsite}>
                <div className="form-row">
                  <label>
                    Website URL
                    <input
                      type="url"
                      value={websiteUrl}
                      onChange={(event) => setWebsiteUrl(event.target.value)}
                      required
                      maxLength={2048}
                      placeholder="https://docs.example.com"
                      disabled={!canManage}
                    />
                  </label>
                  <label>
                    Display name
                    <input
                      value={websiteName}
                      onChange={(event) => setWebsiteName(event.target.value)}
                      maxLength={200}
                      placeholder="Help center"
                      disabled={!canManage}
                    />
                  </label>
                </div>
                <div className="form-row form-row-small">
                  <label>
                    Maximum pages
                    <input
                      type="number"
                      min={1}
                      max={50}
                      value={maxPages}
                      onChange={(event) => setMaxPages(Number(event.target.value))}
                      required
                      disabled={!canManage}
                    />
                  </label>
                  <label>
                    Maximum depth
                    <input
                      type="number"
                      min={0}
                      max={3}
                      value={maxDepth}
                      onChange={(event) => setMaxDepth(Number(event.target.value))}
                      required
                      disabled={!canManage}
                    />
                  </label>
                </div>
                <p className="form-note">
                  The crawler stays on the exact public host and enforces robots, rate, redirect,
                  response-size, and SSRF limits.
                </p>
                <div className="builder-submit">
                  <button className="button button-primary" type="submit" disabled={busy || !canManage}>
                    {busy ? "Queuing…" : "Start bounded crawl"}
                  </button>
                </div>
              </form>
            ) : null}

            {mode === "manual" ? (
              <form className="builder-panel workspace-form" aria-label="Manual source" onSubmit={saveManual}>
                <label>
                  Entry name
                  <input
                    value={manualName}
                    onChange={(event) => setManualName(event.target.value)}
                    maxLength={200}
                    placeholder="Refund window"
                    disabled={!canManage}
                  />
                </label>
                <label>
                  Customer question
                  <textarea
                    value={manualQuestion}
                    onChange={(event) => setManualQuestion(event.target.value)}
                    required
                    rows={3}
                    maxLength={2000}
                    placeholder="How long do I have to request a refund?"
                    disabled={!canManage}
                  />
                </label>
                <label>
                  Authoritative answer
                  <textarea
                    value={manualAnswer}
                    onChange={(event) => setManualAnswer(event.target.value)}
                    required
                    rows={6}
                    maxLength={20000}
                    placeholder="Refund requests are accepted within…"
                    disabled={!canManage}
                  />
                </label>
                <div className="builder-submit">
                  {editingManual ? (
                    <button className="button button-quiet" type="button" onClick={clearManual} disabled={busy}>
                      Cancel edit
                    </button>
                  ) : null}
                  <button className="button button-primary" type="submit" disabled={busy || !canManage}>
                    {busy ? "Saving…" : editingManual ? "Update answer" : "Add manual answer"}
                  </button>
                </div>
              </form>
            ) : null}
          </section>

          <section className="source-library" aria-labelledby="source-library-title">
            <div className="library-heading">
              <div>
                <span className="eyebrow">Source library</span>
                <h2 id="source-library-title">
                  {sources.length} connected source{sources.length === 1 ? "" : "s"}
                </h2>
              </div>
              <div className="library-actions">
                {shouldPoll ? <span className="polling-note"><span />Auto-refreshing</span> : null}
                <button
                  className="button button-quiet"
                  type="button"
                  onClick={() => void loadSources(selectedBotId, true)}
                  disabled={sourceLoading}
                >
                  {sourceLoading ? "Refreshing…" : "Refresh status"}
                </button>
              </div>
            </div>
            {sourceLoading && sources.length === 0 ? (
              <div className="skeleton source-list-skeleton" />
            ) : sources.length === 0 ? (
              <div className="source-empty"><p>No knowledge is connected to this bot yet.</p></div>
            ) : (
              <div className="source-list" aria-live="polite">
                {sources.map((source) => (
                  <article className="source-row" key={source.id}>
                    <span className={`source-type-icon source-type-${source.type}`}>
                      {sourceIcon(source.type)}
                    </span>
                    <div className="source-copy">
                      <div className="source-title-row">
                        <h3>{source.name}</h3>
                        <span className={`state-badge state-${source.status}`}>
                          <span />{source.status}
                        </span>
                      </div>
                      <p>{detailString(source)}</p>
                      {source.error_message ? (
                        <div className="source-error" role="alert">
                          {source.error_message}
                          {source.error_code ? <small>Reference: {source.error_code}</small> : null}
                        </div>
                      ) : null}
                      <small>Updated {new Date(source.updated_at).toLocaleString()}</small>
                    </div>
                    {canManage ? (
                      <div className="source-actions">
                        {source.type === "manual" ? (
                          <button
                            className="icon-action"
                            type="button"
                            aria-label={`Edit ${source.name}`}
                            onClick={() => startManualEdit(source)}
                            disabled={busy}
                          >
                            <EditIcon width={16} height={16} />
                          </button>
                        ) : null}
                        <button
                          className="icon-action icon-action-danger"
                          type="button"
                          aria-label={`Delete ${source.name}`}
                          onClick={() => setDeleting(source)}
                          disabled={busy}
                        >
                          <TrashIcon width={16} height={16} />
                        </button>
                      </div>
                    ) : null}
                  </article>
                ))}
              </div>
            )}
          </section>
        </>
      )}

      {deleting ? (
        <div className="dialog-backdrop" role="presentation">
          <section
            className="workspace-dialog workspace-dialog-small"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="delete-source-title"
            aria-describedby="delete-source-copy"
          >
            <span className="danger-icon"><TrashIcon width={21} height={21} /></span>
            <h2 id="delete-source-title">Remove {deleting.name}?</h2>
            <p id="delete-source-copy">
              The source and its indexed document versions will be removed from this bot. This
              cannot be undone.
            </p>
            <div className="dialog-actions">
              <button ref={keepSourceRef} className="button button-quiet" type="button" onClick={() => setDeleting(null)} disabled={busy}>
                Keep source
              </button>
              <button className="button button-danger" type="button" disabled={busy} onClick={() => void confirmDelete()}>
                {busy ? "Removing…" : "Remove source"}
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
