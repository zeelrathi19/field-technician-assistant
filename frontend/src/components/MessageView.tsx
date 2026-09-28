import type { ChatMessage, KnowledgeSource, WorkOrderCard, ActionReceipt } from "../types";
import { StatusPill } from "./StatusPill";

const OUTCOME_LABEL: Record<string, string> = {
  answered: "Answer",
  acted: "Done",
  refused: "Not done",
  clarification: "Needs detail",
  error: "Error",
};

function Receipt({ a }: { a: ActionReceipt }) {
  if (!a.tool) return null;
  const label = a.tool === "update_status" ? "Status change" : a.tool === "add_note" ? "Note" : a.tool === "escalate" ? "Escalation" : a.tool;
  return (
    <div className={`receipt ${a.ok ? "ok" : "no"}`}>
      <strong>{a.ok ? "✓" : "✕"} {label}</strong>
      {a.work_order_id && <span> · {a.work_order_id}</span>}
      {a.ok && a.previousStatus && a.status && (
        <span>
          {" "}· {a.previousStatus} → {a.status}
        </span>
      )}
      {a.ok && a.text && <span className="payload"> · “{a.text}”</span>}
      {a.ok && a.reason && <span className="payload"> · “{a.reason}”</span>}
      <span className="code">
        {a.code}
        {a.version ? ` · v${a.version}` : ""}
      </span>
    </div>
  );
}

function Card({ c }: { c: WorkOrderCard }) {
  return (
    <div className="wo-card">
      <div className="wo-card-head">
        <strong>{c.id}</strong> <StatusPill status={c.status} />
        {c.escalated && <span className="flag">⚑ escalated</span>}
      </div>
      <div className="wo-card-title">{c.title}</div>
      <div className="wo-meta">
        {c.assetType} · due {c.dueDate} · {c.allowedNextStatus ? `next allowed: ${c.allowedNextStatus}` : "no further status changes"}
      </div>
      {c.steps.length > 0 && (
        <>
          <div className="label">Recorded tasks (from the work order, not verified procedure)</div>
          <ol>
            {c.steps.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ol>
        </>
      )}
      {c.notes && c.notes.length > 0 && (
        <>
          <div className="label">Latest notes</div>
          <ul className="notes">
            {c.notes.map((n) => (
              <li key={n.id}>{n.text}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function Source({ s }: { s: KnowledgeSource }) {
  return (
    <details className="source">
      <summary>
        {s.related ? "Related safety: " : ""}
        <span className="sid">{s.section_id}</span> {s.heading}
      </summary>
      {s.quotes.length > 0 && (
        <div className="quotes">
          {s.quotes.map((q, i) => (
            <blockquote key={i}>{q}</blockquote>
          ))}
        </div>
      )}
      <pre className="section-text">{s.text.replace(/\*\*/g, "")}</pre>
      <div className="hash">source hash {s.content_hash}</div>
    </details>
  );
}

export function MessageView({ message: m }: { message: ChatMessage }) {
  if (m.role === "user") {
    return (
      <div className={`msg user ${m.pending ? "pending" : ""}`}>
        <div className="bubble">{m.text}</div>
      </div>
    );
  }
  const outcome = m.outcome ?? "answered";
  return (
    <div className={`msg assistant out-${outcome}`}>
      <div className="bubble">
        <div className="badges">
          <span className={`badge b-${outcome}`}>{OUTCOME_LABEL[outcome] ?? outcome}</span>
          {outcome === "answered" && m.sources && m.sources.length > 0 && (
            <span className={`badge ${m.verified ? "b-verified" : "b-fallback"}`}>
              {m.verified ? "Verified against sources" : "Exact source text"}
            </span>
          )}
        </div>
        {m.action && <Receipt a={m.action} />}
        <div className="text">{m.text}</div>
        {m.cards?.map((c) => <Card key={`${c.id}-${c.version}`} c={c} />)}
        {m.sources && m.sources.length > 0 && (
          <div className="sources">
            {m.sources.map((s) => (
              <Source key={s.section_id} s={s} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
