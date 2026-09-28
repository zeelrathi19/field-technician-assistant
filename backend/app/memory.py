"""Conversation memory: server-owned session focus + bounded history + per-turn context.

Focus is a *reference*, never permission. It is resolved from the technician's own
words (explicit IDs) and from successful tool results — never from model text,
notes or knowledge-base passages.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .db import dumps, new_id, utcnow
from .intent import extract_ids
from .llm.base import ModelMessage


@dataclass
class SessionState:
    id: str
    user_id: str
    browser_id: str
    focus_id: str | None = None
    candidates: list[str] = field(default_factory=list)
    pending: dict[str, Any] | None = None

    def public(self) -> dict[str, Any]:
        return {"active_work_order_id": self.focus_id, "candidates": list(self.candidates),
                "needs_clarification": bool(self.pending) or bool(self.candidates and not self.focus_id)}


class SessionStore:
    @staticmethod
    def create(conn: sqlite3.Connection, user_id: str, browser_id: str) -> SessionState:
        sid, now = new_id(), utcnow()
        conn.execute("INSERT INTO sessions (id, user_id, browser_id, created_at, updated_at) VALUES (?,?,?,?,?)",
                     (sid, user_id, browser_id, now, now))
        return SessionState(sid, user_id, browser_id)

    @staticmethod
    def load(conn: sqlite3.Connection, session_id: str, user_id: str, browser_id: str) -> SessionState | None:
        row = conn.execute("SELECT * FROM sessions WHERE id=? AND user_id=? AND browser_id=?",
                           (session_id, user_id, browser_id)).fetchone()
        if row is None:
            return None
        return SessionState(row["id"], row["user_id"], row["browser_id"], row["focus_id"],
                            json.loads(row["candidates_json"]),
                            json.loads(row["pending_json"]) if row["pending_json"] else None)

    @staticmethod
    def save(conn: sqlite3.Connection, st: SessionState) -> None:
        conn.execute("UPDATE sessions SET focus_id=?, candidates_json=?, pending_json=?, updated_at=? WHERE id=?",
                     (st.focus_id, dumps(st.candidates), dumps(st.pending) if st.pending else None, utcnow(), st.id))

    @staticmethod
    def append_message(conn: sqlite3.Connection, session_id: str, request_id: str | None, role: str,
                       content: str, payload: dict[str, Any] | None = None) -> str:
        seq = conn.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM messages WHERE session_id=?",
                           (session_id,)).fetchone()[0]
        mid = new_id()
        conn.execute("INSERT INTO messages VALUES (?,?,?,?,?,?,?,?)",
                     (mid, session_id, request_id, seq, role, content, dumps(payload or {}), utcnow()))
        return mid

    @staticmethod
    def messages(conn: sqlite3.Connection, session_id: str, limit: int = 200) -> list[dict[str, Any]]:
        rows = conn.execute(
            "SELECT id, request_id, role, content, payload_json, created_at FROM messages WHERE session_id=? "
            "ORDER BY seq DESC LIMIT ?", (session_id, limit)).fetchall()
        return [{"id": r["id"], "request_id": r["request_id"], "role": r["role"], "text": r["content"],
                 **json.loads(r["payload_json"]), "created_at": r["created_at"]} for r in reversed(rows)]


@dataclass
class FocusResolution:
    explicit_ids: list[str]
    owned_ids: list[str]
    unavailable_ids: list[str]
    focus_id: str | None
    focus_from_earlier_turn: bool
    candidates: list[str]


def resolve_focus(state: SessionState, message: str, owned: set[str]) -> FocusResolution:
    """Deterministic, model-independent focus update from the technician's own text."""
    ids = extract_ids(message)
    owned_ids = [i for i in ids if i in owned]
    unavailable = [i for i in ids if i not in owned]
    if len(ids) == 1:
        # An explicit owned ID becomes focus; an unavailable one clears focus (no stale fallback).
        return FocusResolution(ids, owned_ids, unavailable, owned_ids[0] if owned_ids else None, False, [])
    if len(ids) > 1:
        return FocusResolution(ids, owned_ids, unavailable, None, False, owned_ids)
    return FocusResolution(ids, [], [], state.focus_id, state.focus_id is not None, list(state.candidates))


class ContextBuilder:
    def __init__(self, history_messages: int, history_char_budget: int):
        self.history_messages = history_messages
        self.char_budget = history_char_budget

    def history(self, stored: list[dict[str, Any]]) -> tuple[list[ModelMessage], int]:
        """Newest-first fit of completed user/assistant messages; returns (messages, dropped)."""
        picked: list[ModelMessage] = []
        used = 0
        candidates = [m for m in stored if m["role"] in ("user", "assistant")][-self.history_messages:] \
            if self.history_messages else []
        for m in reversed(candidates):
            text = m["text"]
            if m["role"] == "assistant" and m.get("action"):
                a = m["action"]
                text = f"[server receipt: {a.get('tool')} {a.get('work_order_id')} -> {a.get('code')}] {text}"
            if used + len(text) > self.char_budget:
                break
            used += len(text)
            picked.append(ModelMessage(role=m["role"], content=text))
        picked.reverse()
        # Providers expect the history to start with a user turn.
        while picked and picked[0].role != "user":
            picked.pop(0)
        dropped = len([m for m in stored if m["role"] in ("user", "assistant")]) - len(picked)
        return picked, dropped

    @staticmethod
    def server_context(principal: dict[str, str], res: FocusResolution, roster: list[dict[str, Any]],
                       pending: dict[str, Any] | None) -> ModelMessage:
        ctx = {
            "technician": {"id": principal["id"], "name": principal["name"]},
            "today": date.today().isoformat(),
            "active_work_order": res.focus_id,
            "ambiguous_candidates": res.candidates if not res.focus_id else [],
            "ids_in_this_message": res.explicit_ids,
            "unavailable_ids_in_this_message": res.unavailable_ids,
            "pending_clarification": pending.get("question") if pending else None,
            "my_work_orders": [{k: w[k] for k in ("id", "title", "assetType", "status", "dueDate", "allowedNextStatus")}
                               for w in roster],
        }
        return ModelMessage(role="context", content="<server_context>\n" + json.dumps(ctx, indent=1) + "\n</server_context>")

    @staticmethod
    def user_message(text: str) -> ModelMessage:
        # Neutralise attempts to fake the server block inside user text.
        safe = text.replace("<server_context>", "&lt;server_context&gt;").replace("</server_context>", "&lt;/server_context&gt;")
        return ModelMessage(role="user", content=safe)
