import { API_VERSION } from "@support-agent/api-client";
import { render } from "preact";
import { useEffect, useRef, useState } from "preact/hooks";

import { widgetStyles } from "./styles";

interface WidgetProps {
  apiBase: string;
  publishableKey: string;
  welcome: string;
  accent: string;
  title: string;
}

interface Citation {
  ordinal: number;
  title: string | null;
  canonical_url: string | null;
}

interface Message {
  id: string;
  role: "user" | "agent";
  text: string;
  pending?: boolean;
  citations?: Citation[];
}

interface Frame {
  event: string;
  data: Record<string, unknown>;
}

function endpoint(base: string, key: string, suffix: "sessions" | "messages"): string {
  const normalized = base.replace(/\/$/, "");
  const versioned = normalized.endsWith(`/${API_VERSION}`)
    ? normalized
    : `${normalized}/${API_VERSION}`;
  return `${versioned}/widget/${encodeURIComponent(key)}/${suffix}`;
}

function parseFrame(raw: string): Frame | null {
  let event = "message";
  const data: string[] = [];
  for (const rawLine of raw.split("\n")) {
    const line = rawLine.replace(/\r$/, "");
    if (line.startsWith("event:")) event = line.slice(6).trim();
    if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  if (!data.length) return null;
  const parsed: unknown = JSON.parse(data.join("\n"));
  return {
    event,
    data: typeof parsed === "object" && parsed !== null
      ? parsed as Record<string, unknown>
      : {},
  };
}

function ChatIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 18.4 3.5 21l3.8-1.2c1.3.7 2.9 1.1 4.7 1.1 5 0 9-3.7 9-8.4S17 4 12 4s-9 3.7-9 8.5c0 2.2.8 4.2 2 5.9Z"/><path d="M8 12.5h.01M12 12.5h.01M16 12.5h.01"/></svg>;
}

function SendIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m4 4 17 8-17 8 3-8-3-8Z"/><path d="M7 12h14"/></svg>;
}

function Widget({ apiBase, publishableKey, welcome, accent, title }: WidgetProps) {
  const [open, setOpen] = useState(false);
  const [sessionToken, setSessionToken] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryQuestion, setRetryQuestion] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (open) window.setTimeout(() => inputRef.current?.focus(), 0);
  }, [open]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages]);

  useEffect(() => () => abortRef.current?.abort(), []);

  async function ensureSession(): Promise<string> {
    if (sessionToken) return sessionToken;
    if (!apiBase || !publishableKey) throw new Error("This support widget is not configured.");
    const response = await fetch(endpoint(apiBase, publishableKey, "sessions"), {
      method: "POST",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    const payload = await response.json().catch(() => null) as {
      session_token?: unknown;
      detail?: unknown;
    } | null;
    if (!response.ok || typeof payload?.session_token !== "string") {
      throw new Error(typeof payload?.detail === "string" ? payload.detail : "Support is unavailable right now.");
    }
    setSessionToken(payload.session_token);
    return payload.session_token;
  }

  function patchMessage(id: string, update: Partial<Message>) {
    setMessages((current) => current.map((item) => item.id === id ? { ...item, ...update } : item));
  }

  async function send(questionOverride?: string) {
    const question = (questionOverride ?? draft).trim();
    if (!question || busy) return;
    setDraft("");
    setBusy(true);
    setError(null);
    setRetryQuestion(null);
    const assistantId = crypto.randomUUID();
    setMessages((current) => [
      ...current,
      { id: crypto.randomUUID(), role: "user", text: question },
      { id: assistantId, role: "agent", text: "", pending: true },
    ]);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const token = await ensureSession();
      const response = await fetch(endpoint(apiBase, publishableKey, "messages"), {
        method: "POST",
        headers: {
          Accept: "text/event-stream",
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ message: question }),
        cache: "no-store",
        signal: controller.signal,
      });
      if (!response.ok || !response.body) {
        const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
        if (response.status === 401) setSessionToken(null);
        throw new Error(typeof payload?.detail === "string" ? payload.detail : "The answer could not start.");
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let text = "";
      while (true) {
        const { done, value } = await reader.read();
        buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, "\n");
        let boundary = buffer.indexOf("\n\n");
        while (boundary !== -1) {
          const frame = parseFrame(buffer.slice(0, boundary));
          buffer = buffer.slice(boundary + 2);
          if (frame?.event === "text_delta") {
            text += String(frame.data.text ?? "");
            patchMessage(assistantId, { text });
          } else if (frame?.event === "replace_text") {
            text = String(frame.data.text ?? "");
            patchMessage(assistantId, { text });
          } else if (frame?.event === "citations") {
            patchMessage(assistantId, { citations: (frame.data.citations ?? []) as Citation[] });
          } else if (frame?.event === "completed") {
            patchMessage(assistantId, { pending: false });
          } else if (frame?.event === "error") {
            throw new Error(String(frame.data.message ?? "The answer could not be completed."));
          }
          boundary = buffer.indexOf("\n\n");
        }
        if (done) break;
      }
      patchMessage(assistantId, { pending: false });
    } catch (caught) {
      if (controller.signal.aborted) return;
      patchMessage(assistantId, { pending: false, text: "I couldn't complete that answer." });
      setError(caught instanceof Error ? caught.message : "Support is temporarily unavailable.");
      setRetryQuestion(question);
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      setBusy(false);
    }
  }

  function close() {
    abortRef.current?.abort();
    setBusy(false);
    setOpen(false);
  }

  return (
    <div style={{ "--sa-accent": accent } as Record<string, string>}>
      {open ? (
        <section className="panel" role="dialog" aria-modal="false" aria-label={`${title} support chat`}>
          <header className="header">
            <div className="identity"><strong>{title}</strong><span>Typically replies in moments</span></div>
            <button className="close" type="button" onClick={close} aria-label="Close support chat">×</button>
          </header>
          <div className="messages" aria-live="polite" aria-busy={busy}>
            {messages.length === 0 ? (
              <div className="welcome">
                <span className="welcome-icon"><ChatIcon /></span>
                <strong>{welcome}</strong>
                <p>Ask a question and we’ll answer from the available support knowledge.</p>
              </div>
            ) : messages.map((message) => (
              <div className={`bubble bubble-${message.role}`} key={message.id}>
                {message.pending && !message.text ? (
                  <span className="typing" aria-label="Agent is typing"><i/><i/><i/></span>
                ) : message.text}
                {message.citations?.length ? (
                  <div className="citations" aria-label="Sources">
                    {message.citations.map((citation) => citation.canonical_url ? (
                      <a href={citation.canonical_url} target="_blank" rel="noreferrer" key={citation.ordinal}>[{citation.ordinal}] {citation.title || "Source"}</a>
                    ) : <span key={citation.ordinal}>[{citation.ordinal}] {citation.title || "Source"}</span>)}
                  </div>
                ) : null}
              </div>
            ))}
            <div ref={endRef}/>
          </div>
          <div>
            {error ? <div className="error" role="alert">{error}{retryQuestion ? <><br/><button className="retry" type="button" onClick={() => void send(retryQuestion)}>Retry last question</button></> : null}</div> : null}
            <form className="composer" onSubmit={(event) => { event.preventDefault(); void send(); }}>
              <div className="composer-row">
                <label className="sr-only" htmlFor="sa-message">Message support</label>
                <textarea ref={inputRef} id="sa-message" value={draft} onInput={(event) => setDraft(event.currentTarget.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} rows={1} maxLength={20000} placeholder="Type your question…" disabled={busy}/>
                <button className="send" type="submit" disabled={busy || !draft.trim()} aria-label="Send message"><SendIcon /></button>
              </div>
              <small className="powered">Powered by Support Agent</small>
            </form>
          </div>
        </section>
      ) : null}
      <button className="launcher" type="button" onClick={() => setOpen((value) => !value)} aria-label="Open support chat" aria-expanded={open}><ChatIcon /></button>
    </div>
  );
}

function safeAccent(value: string | null): string {
  const candidate = value?.trim() || "#194f46";
  return CSS.supports("color", candidate) ? candidate : "#194f46";
}

class SupportAgentElement extends HTMLElement {
  static observedAttributes = ["api-base", "publishable-key", "welcome", "accent", "title"];

  readonly root: ShadowRoot;
  readonly mountPoint: HTMLDivElement;

  constructor() {
    super();
    this.root = this.attachShadow({ mode: "open" });
    const style = document.createElement("style");
    style.textContent = widgetStyles;
    this.mountPoint = document.createElement("div");
    this.root.append(style, this.mountPoint);
  }

  connectedCallback() { this.mount(); }
  attributeChangedCallback() { if (this.isConnected) this.mount(); }
  disconnectedCallback() { render(null, this.mountPoint); }

  private mount() {
    render(
      <Widget
        apiBase={this.getAttribute("api-base") ?? ""}
        publishableKey={this.getAttribute("publishable-key") ?? ""}
        welcome={this.getAttribute("welcome")?.trim() || "How can we help?"}
        accent={safeAccent(this.getAttribute("accent"))}
        title={this.getAttribute("title")?.trim() || "Support"}
      />,
      this.mountPoint,
    );
  }
}

if (!customElements.get("support-agent")) {
  customElements.define("support-agent", SupportAgentElement);
}

export { SupportAgentElement };
