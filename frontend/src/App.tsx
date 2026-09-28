import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, uuid } from "./api";
import type { ChatMessage, Meta, RosterItem, SessionState } from "./types";
import { MessageView } from "./components/MessageView";
import { Composer } from "./components/Composer";
import { WorkOrderPanel } from "./components/WorkOrderPanel";

const SESSION_KEY = "fta.session";
const EXAMPLES = [
  "How do I reset a CU-series unit?",
  "Show WO-003",
  "Mark it complete",
  "What torque should I use on the compressor bolts?",
  "Add a note to WO-002: filter replaced",
  "Escalate WO-006 because exposed wiring was found",
];

interface Failure {
  message: string;
  retryable: boolean;
  requestId: string;
  text: string;
}

function readStored(): string | null {
  try {
    return localStorage.getItem(SESSION_KEY);
  } catch {
    return null;
  }
}
function store(id: string) {
  try {
    localStorage.setItem(SESSION_KEY, id);
  } catch {
    /* storage unavailable: session simply won't survive reload */
  }
}

export default function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [state, setState] = useState<SessionState | null>(null);
  const [roster, setRoster] = useState<RosterItem[]>([]);
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [draft, setDraft] = useState("");
  const [bootError, setBootError] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const refreshRoster = useCallback(() => {
    api.roster().then((r) => setRoster(r.work_orders)).catch(() => undefined);
  }, []);

  const newChat = useCallback(async () => {
    const s = await api.createSession();
    store(s.session_id);
    setSessionId(s.session_id);
    setMessages([]);
    setState(s.state);
    setFailure(null);
  }, []);

  useEffect(() => {
    (async () => {
      try {
        setMeta(await api.meta());
        refreshRoster();
        const stored = readStored();
        if (stored) {
          try {
            const s = await api.getSession(stored);
            setSessionId(s.session_id);
            setMessages(s.messages);
            setState(s.state);
            return;
          } catch {
            /* stale or foreign session: start fresh */
          }
        }
        await newChat();
      } catch {
        setBootError("Can't reach the assistant server. Is it running on this address?");
      }
    })();
  }, [newChat, refreshRoster]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, pending]);

  const send = useCallback(
    async (text: string, requestId: string = uuid()) => {
      if (!sessionId || pending) return;
      setPending(true);
      setFailure(null);
      const optimistic: ChatMessage = { id: `local-${requestId}`, role: "user", text, pending: true };
      setMessages((m) => [...m.filter((x) => x.id !== optimistic.id), optimistic]);
      try {
        const res = await api.send(sessionId, requestId, text);
        setMessages((m) => [...m.filter((x) => x.id !== optimistic.id), ...res.messages]);
        setState(res.state);
        setDraft("");
        if (res.action?.ok) refreshRoster();
      } catch (e) {
        const err = e instanceof ApiError ? e : new ApiError(0, { message: String(e) }, true);
        if (err.status === 404) {
          setFailure({ message: "This chat is no longer available. Start a new chat.", retryable: false, requestId, text });
        } else {
          setFailure({ message: err.message, retryable: err.retryable, requestId, text });
        }
        setMessages((m) => m.filter((x) => x.id !== optimistic.id));
        setDraft(text); // never lose the technician's words
      } finally {
        setPending(false);
        // Return focus to the message box so keyboard users can keep going.
        requestAnimationFrame(() => inputRef.current?.focus());
      }
    },
    [sessionId, pending, refreshRoster],
  );

  if (bootError) {
    return (
      <div className="boot-error" role="alert">
        <h1>Field Technician Assistant</h1>
        <p>{bootError}</p>
        <button onClick={() => location.reload()}>Try again</button>
      </div>
    );
  }

  return (
    <div className="app">
      <a className="skip" href="#msg" onClick={(e) => { e.preventDefault(); inputRef.current?.focus(); }}>
        Skip to message box
      </a>
      <header className="topbar">
        <div className="brand">
          <span className="logo" aria-hidden>
            ⚙
          </span>
          <div>
            <h1>Field Technician Assistant</h1>
            <p className="sub">{meta ? `Signed in as ${meta.technician.name}` : "Connecting…"}</p>
          </div>
        </div>
        <div className="top-actions">
          {meta && (
            <span className={`mode ${meta.is_llm ? "mode-llm" : "mode-offline"}`} title={`Prompt ${meta.prompt_version} · KB ${meta.kb_hash}`}>
              {meta.is_llm ? `${meta.provider} · ${meta.model}` : "Offline heuristic mode — not an LLM"}
            </span>
          )}
          <button className="ghost panel-toggle" aria-expanded={panelOpen} aria-controls="orders" onClick={() => setPanelOpen((v) => !v)}>
            My work orders
          </button>
          <button className="ghost" onClick={() => newChat()} disabled={pending}>
            New chat
          </button>
        </div>
      </header>

      <div className="layout">
        <main className="chat" aria-label="Conversation">
          <div className="messages" role="log" aria-live="polite" aria-relevant="additions" aria-busy={pending}>
            {messages.length === 0 && (
              <div className="empty">
                <h2>Ask about maintenance or your work orders</h2>
                <p>
                  Answers come only from the approved knowledge base, with the exact source text. Changes are checked by the server:
                  only your own work orders, one status step at a time (Open → In Progress → On Hold → Completed).
                </p>
                <div className="chips">
                  {EXAMPLES.map((ex) => (
                    <button key={ex} className="chip" onClick={() => send(ex)} disabled={pending || !sessionId}>
                      {ex}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((m) => (
              <MessageView key={m.id} message={m} />
            ))}
            {pending && (
              <div className="msg assistant thinking" role="status" aria-label="Assistant is working">
                <span className="dot" />
                <span className="dot" />
                <span className="dot" />
              </div>
            )}
            <div ref={endRef} />
          </div>

          {failure && (
            <div className="failure" role="alert">
              <span>⚠ {failure.message}</span>
              {failure.retryable && (
                <button onClick={() => send(failure.text, failure.requestId)} disabled={pending}>
                  Retry
                </button>
              )}
              {!failure.retryable && failure.message.includes("New chat") && <button onClick={() => newChat()}>New chat</button>}
            </div>
          )}

          <Composer
            value={draft}
            onChange={setDraft}
            onSend={(t) => send(t)}
            disabled={pending || !sessionId}
            maxChars={meta?.limits.max_message_chars ?? 8000}
            context={state}
            inputRef={inputRef}
          />
        </main>

        <WorkOrderPanel id="orders" open={panelOpen} items={roster} active={state?.active_work_order_id ?? null} onAsk={(t) => send(t)} disabled={pending} />
      </div>
    </div>
  );
}
