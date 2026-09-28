import type { RosterItem } from "../types";
import { StatusPill } from "./StatusPill";

interface Props {
  id: string;
  open: boolean;
  items: RosterItem[];
  active: string | null;
  onAsk: (text: string) => void;
  disabled: boolean;
}

export function WorkOrderPanel({ id, open, items, active, onAsk, disabled }: Props) {
  return (
    <aside id={id} className={`panel ${open ? "open" : ""}`} aria-label="My work orders">
      <h2>My work orders</h2>
      <p className="panel-note">Read directly from the database (not generated). Only orders assigned to you are shown.</p>
      <ul>
        {items.map((w) => (
          <li key={w.id} className={w.id === active ? "active" : ""}>
            <button className="wo" onClick={() => onAsk(`Show ${w.id}`)} disabled={disabled} aria-current={w.id === active}>
              <span className="wo-top">
                <span className="wo-id">{w.id}</span>
                <StatusPill status={w.status} />
              </span>
              <span className="wo-title">{w.title}</span>
              <span className="wo-meta">
                {w.assetType} · due {w.dueDate}
                {w.noteCount > 0 && ` · ${w.noteCount} note${w.noteCount > 1 ? "s" : ""}`}
                {w.escalated && <span className="flag"> · ⚑ escalated</span>}
              </span>
              <span className="wo-next">{w.allowedNextStatus ? `Next allowed: ${w.allowedNextStatus}` : "Terminal: no further status changes"}</span>
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}
