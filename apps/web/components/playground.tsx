"use client";

import type {
  BotResponse,
  UsageSummaryResponse,
} from "@support-agent/api-client";
import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { MessageIcon, SparkIcon } from "@/components/icons";
import { dashboardApi, dashboardStream } from "@/lib/dashboard-api";

interface Citation {
  ordinal: number;
  source_id: string;
  document_id: string;
  title: string | null;
  canonical_url: string | null;
  chunk_ordinal: number;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  citations?: Citation[];
  pending?: boolean;
  fallback?: boolean;
  responseKind?: "grounded" | "fallback" | "local_greeting";
}

interface SseFrame {
  event: string;
  data: Record<string, unknown>;
}

function parseFrame(frame: string): SseFrame | null {
  let event = "message";
  const data: string[] = [];
  for (const rawLine of frame.split("\n")) {
    const line = rawLine.replace(/\r$/, "");
    if (line.startsWith("event:")) event = line.slice(6).trim();
    if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  if (data.length === 0) return null;
  const parsed: unknown = JSON.parse(data.join("\n"));
  return {
    event,
    data:
      typeof parsed === "object" && parsed !== null
        ? (parsed as Record<string, unknown>)
        : {},
  };
}

function formatCost(microusd: number): string {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: microusd >= 1_000_000 ? 2 : 4,
    maximumFractionDigits: 6,
  }).format(microusd / 1_000_000);
}

export function Playground() {
  const [bots, setBots] = useState<BotResponse[]>([]);
  const [selectedBotId, setSelectedBotId] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [usage, setUsage] = useState<UsageSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retrievalState, setRetrievalState] = useState("Ready for a grounded question");
  const abortRef = useRef<AbortController | null>(null);
  const messageEndRef = useRef<HTMLDivElement>(null);

  const loadUsage = useCallback(async (botId?: string) => {
    try {
      setUsage(await dashboardApi.usageSummary(botId));
    } catch {
      setUsage(null);
    }
  }, []);

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
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "Bots could not be loaded.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    void loadUsage();
    return () => {
      cancelled = true;
      abortRef.current?.abort();
    };
  }, [loadUsage]);

  useEffect(() => {
    abortRef.current?.abort();
    setConversationId(null);
    setMessages([]);
    setError(null);
    setRetrievalState("Ready for a grounded question");
    if (selectedBotId) void loadUsage(selectedBotId);
  }, [loadUsage, selectedBotId]);

  useEffect(() => {
    messageEndRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages]);

  async function newSession(): Promise<string> {
    if (!selectedBotId) throw new Error("Choose a bot first.");
    const created = await dashboardApi.createPlaygroundSession(selectedBotId);
    setConversationId(created.conversation_id);
    return created.conversation_id;
  }

  async function resetConversation() {
    abortRef.current?.abort();
    setResetting(true);
    setError(null);
    try {
      await newSession();
      setMessages([]);
      setRetrievalState("New conversation ready");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The conversation could not reset.");
    } finally {
      setSending(false);
      setResetting(false);
    }
  }

  function updateAssistant(id: string, update: Partial<ChatMessage>) {
    setMessages((current) =>
      current.map((message) => (message.id === id ? { ...message, ...update } : message)),
    );
  }

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const question = draft.trim();
    if (!question || !selectedBotId || sending) return;
    setDraft("");
    setSending(true);
    setError(null);
    setRetrievalState("Retrieving trusted sources…");
    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      text: question,
    };
    const assistantId = crypto.randomUUID();
    setMessages((current) => [
      ...current,
      userMessage,
      { id: assistantId, role: "assistant", text: "", pending: true },
    ]);

    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const activeConversation = conversationId ?? (await newSession());
      const response = await dashboardStream(
        `/playground/sessions/${encodeURIComponent(activeConversation)}/messages`,
        {
          method: "POST",
          body: JSON.stringify({ message: question }),
          signal: controller.signal,
        },
      );
      if (!response.body) throw new Error("The stream did not start.");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let answer = "";
      while (true) {
        const { done, value } = await reader.read();
        buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, "\n");
        let boundary = buffer.indexOf("\n\n");
        while (boundary !== -1) {
          const frame = parseFrame(buffer.slice(0, boundary));
          buffer = buffer.slice(boundary + 2);
          if (frame?.event === "text_delta") {
            answer += String(frame.data.text ?? "");
            updateAssistant(assistantId, { text: answer });
            setRetrievalState("Streaming grounded answer…");
          } else if (frame?.event === "replace_text") {
            answer = String(frame.data.text ?? "");
            updateAssistant(assistantId, { text: answer });
          } else if (frame?.event === "citations") {
            updateAssistant(assistantId, {
              citations: (frame.data.citations ?? []) as Citation[],
            });
          } else if (frame?.event === "completed") {
            const fallback = Boolean(frame.data.fallback);
            const responseKind = String(
              frame.data.response_kind ?? (fallback ? "fallback" : "grounded"),
            ) as ChatMessage["responseKind"];
            updateAssistant(assistantId, { pending: false, fallback, responseKind });
            setRetrievalState(
              responseKind === "local_greeting"
                ? "Local greeting — no AI credits used"
                : fallback
                  ? "No strong source match — safe fallback used"
                  : "Grounded answer complete",
            );
          } else if (frame?.event === "error") {
            throw new Error(String(frame.data.message ?? "The response failed."));
          }
          boundary = buffer.indexOf("\n\n");
        }
        if (done) break;
      }
      updateAssistant(assistantId, { pending: false });
      await loadUsage(selectedBotId);
    } catch (caught) {
      if (controller.signal.aborted) return;
      const message = caught instanceof Error ? caught.message : "The answer could not be completed.";
      setError(message);
      updateAssistant(assistantId, {
        pending: false,
        text: "I could not complete that turn. You can retry the question.",
      });
      setRetrievalState("Turn failed — ready to retry");
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      setSending(false);
    }
  }

  return (
    <div className="workspace-screen playground-screen">
      <header className="screen-heading screen-heading-compact">
        <div>
          <span className="eyebrow">Test bench</span>
          <h1>Ask it before your customers do.</h1>
          <p>See grounded answers, source citations, and usage in a private tenant session.</p>
        </div>
        <div className="playground-controls">
          <label>
            <span>Bot</span>
            <select
              value={selectedBotId}
              onChange={(event) => setSelectedBotId(event.target.value)}
              disabled={loading || sending}
            >
              {bots.map((bot) => <option value={bot.id} key={bot.id}>{bot.name}</option>)}
            </select>
          </label>
          <button
            className="button button-quiet"
            type="button"
            onClick={() => void resetConversation()}
            disabled={!selectedBotId || resetting}
          >
            {resetting ? "Resetting…" : "Reset chat"}
          </button>
        </div>
      </header>

      {error ? <div className="workspace-alert workspace-alert-error" role="alert">{error}</div> : null}
      {!loading && bots.length === 0 ? (
        <section className="empty-workspace">
          <span className="empty-icon"><MessageIcon width={26} height={26} /></span>
          <h2>Create a bot before opening the playground.</h2>
          <p>The playground keeps each test thread scoped to one bot and organization.</p>
        </section>
      ) : (
        <div className="playground-layout">
          <section className="playground-chat" aria-label="Playground conversation">
            <div className="playground-state" role="status">
              <span className={sending ? "state-dot state-dot-live" : "state-dot"} />
              {retrievalState}
            </div>
            <div className="playground-messages" aria-live="polite">
              {messages.length === 0 ? (
                <div className="playground-welcome">
                  <span><SparkIcon width={23} height={23} /></span>
                  <h2>Start with a real support question.</h2>
                  <p>Try a policy, product, or troubleshooting question covered by your sources.</p>
                </div>
              ) : messages.map((message) => (
                <article className={`chat-bubble chat-bubble-${message.role}`} key={message.id}>
                  <span>{message.role === "user" ? "You" : "Agent"}</span>
                  <p>{message.text || (message.pending ? "Thinking…" : "")}</p>
                  {message.citations?.length ? (
                    <div className="citation-list" aria-label="Sources">
                      {message.citations.map((citation) => (
                        citation.canonical_url ? (
                          <a href={citation.canonical_url} target="_blank" rel="noreferrer" key={`${message.id}-${citation.ordinal}`}>
                            [{citation.ordinal}] {citation.title || "Source"}
                          </a>
                        ) : (
                          <span key={`${message.id}-${citation.ordinal}`}>
                            [{citation.ordinal}] {citation.title || "Source"}
                          </span>
                        )
                      ))}
                    </div>
                  ) : null}
                  {message.fallback ? <small>Safe fallback — no sufficiently strong source match.</small> : null}
                  {message.responseKind === "local_greeting" ? <small>Local reply — no AI credits used.</small> : null}
                </article>
              ))}
              <div ref={messageEndRef} />
            </div>
            <form className="playground-composer" onSubmit={sendMessage}>
              <label className="sr-only" htmlFor="playground-question">Support question</label>
              <textarea
                id="playground-question"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    event.currentTarget.form?.requestSubmit();
                  }
                }}
                rows={2}
                maxLength={20000}
                placeholder="Ask a customer question…"
                disabled={!selectedBotId || sending}
              />
              <button className="button button-primary" type="submit" disabled={!draft.trim() || sending}>
                {sending ? "Answering…" : "Send"}
              </button>
            </form>
          </section>

          <aside className="usage-panel" aria-labelledby="usage-title">
            <div><span className="eyebrow">Usage</span><h2 id="usage-title">Current bot</h2></div>
            <div className="usage-metrics">
              <div><span>Total tokens</span><strong>{usage?.total_tokens.toLocaleString() ?? "—"}</strong></div>
              <div><span>Requests</span><strong>{usage?.event_count.toLocaleString() ?? "—"}</strong></div>
              <div><span>Avg. latency</span><strong>{usage ? `${Math.round(usage.average_latency_ms)} ms` : "—"}</strong></div>
              <div><span>Estimated cost</span><strong>{usage ? formatCost(usage.estimated_cost_microusd) : "—"}</strong></div>
            </div>
            <div className="usage-breakdown">
              <h3>Models</h3>
              {usage?.by_model.length ? usage.by_model.map((item) => (
                <div key={`${item.operation}-${item.provider}-${item.model}`}>
                  <span><strong>{item.model}</strong><small>{item.provider} · {item.operation}</small></span>
                  <b>{item.total_tokens.toLocaleString()} tok</b>
                </div>
              )) : <p>Usage appears after the first completed turn.</p>}
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
