"""Offline heuristic model — NOT an LLM.

A small deterministic rule set that speaks the same tool-calling protocol as the
real adapters. It exists so the full pipeline (dispatcher, intent guard,
verifier, service, UI) can be exercised with no API key: automated e2e tests, a
keyless demo, and CI. It is clearly labelled in the UI. It is not evidence that
an LLM integration works — use ``make smoke`` with a real provider for that.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..intent import (_content, ESCALATE_WORDS, HYPOTHETICAL, NEGATION, NEXT_WORDS, NOTE_WORDS, extract_ids,
                      mentioned_statuses, tokens)
from ..knowledge import KnowledgeBase
from .base import ModelDecision, ModelMessage, ToolCall

KB_TOPICS: list[tuple[str, re.Pattern[str]]] = [
    ("kb-2", re.compile(r"\b(lockout|lock-out|tagout|tag-out|lock|locked|tag|zero energy|bypass)\b", re.I)),
    ("kb-1", re.compile(r"\b(reset\w*|led|amber|blink\w*)\b", re.I)),
    ("kb-3", re.compile(r"\b(warrant\w*|labou?r|void|claim|covered|coverage)\b", re.I)),
    ("kb-4", re.compile(r"\b(when (?:should|do|to) (?:i )?escalat\w*|escalat\w*|supervisor)\b", re.I)),
    ("kb-5", re.compile(r"\b(filters?|af-?\w*|airflow|blower|dust\w*)\b", re.I)),
]
UNSUPPORTED = re.compile(
    r"\b(firmware|flash\w*|torque|bolts?|pressure|psi|refrigerant|price|cost|voltage|volts|calibrat\w*|password|"
    r"wiring diagram|part numbers?|stock)\b", re.I)
READ_WORDS = re.compile(r"\b(show|details?|look ?up|what(?:'s| is)|status|steps?|open up|tell me about|check|view|due)\b", re.I)
ROSTER_WORDS = re.compile(r"\b(my (?:work orders|jobs|orders|tasks)|on my plate|assigned to me|what do i have|list)\b", re.I)
GREETING = re.compile(r"^\s*(hi|hello|hey|thanks|thank you|ok|okay)\b", re.I)


def _items(body: str) -> list[str]:
    items: list[str] = []
    for line in body.splitlines():
        if not line.strip():
            continue
        clean = re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", line).replace("**", "").strip()
        if re.match(r"^\s*(?:[-*]|\d+\.)\s+", line) or not items or line[:1] not in (" ", "\t"):
            if items and not re.match(r"^\s*(?:[-*]|\d+\.)\s+", line) and not items[-1].endswith((".", ":")):
                items[-1] += " " + clean
            else:
                items.append(clean)
        else:
            items[-1] += " " + clean
    return items


class OfflineModel:
    provider = "offline"
    model = "offline-heuristic (not an LLM)"
    is_llm = False

    def __init__(self, kb: KnowledgeBase):
        self.kb = kb
        self._n = 0

    # ---- protocol -------------------------------------------------------------------------
    def generate(self, system: str, messages: list[ModelMessage], tools: list[dict[str, Any]], *,
                 max_output_tokens: int, timeout: float) -> ModelDecision:
        ctx = self._context(messages)
        last = messages[-1]
        if last.role == "tool":
            return self._after_tool(last, ctx)
        user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        return self._plan(user, ctx)

    def _id(self) -> str:
        self._n += 1
        return f"offline_{self._n}"

    def _call(self, name: str, args: dict[str, Any]) -> ModelDecision:
        return ModelDecision((ToolCall(self._id(), name, json.dumps(args)),), finish_reason="tool_calls")

    def _respond(self, kind: str, text: str, citations: list[dict[str, str]] | None = None,
                 missing: list[str] | None = None) -> ModelDecision:
        return self._call("respond", {"kind": kind, "text": text, "citations": citations or [], "missing": missing or []})

    @staticmethod
    def _context(messages: list[ModelMessage]) -> dict[str, Any]:
        for m in reversed(messages):
            if m.role == "context" and "<server_context>" in m.content:
                body = m.content.split("<server_context>", 1)[1].rsplit("</server_context>", 1)[0]
                return json.loads(body)
        return {}

    # ---- after a tool result ----------------------------------------------------------------
    def _after_tool(self, msg: ModelMessage, ctx: dict[str, Any]) -> ModelDecision:
        result = json.loads(msg.content)
        if not result.get("ok"):
            return self._respond("refuse", result.get("message", "That isn't available."))
        d = result["data"]
        steps = "; ".join(d.get("steps", []))
        text = (f"{d['id']}: {d['title']} ({d['assetType']}). Status: {d['status']}. Due {d['dueDate']}. "
                f"Recorded steps: {steps}.")
        if d.get("allowedNextStatus"):
            text += f" Next allowed status: {d['allowedNextStatus']}."
        if d.get("notes"):
            text += f" Latest note: {d['notes'][0]['text']}"
        return self._respond("answer", text[:1200])

    # ---- planning from the user's message --------------------------------------------------------
    def _plan(self, text: str, ctx: dict[str, Any]) -> ModelDecision:
        ids = extract_ids(text)
        focus = ctx.get("active_work_order")
        target = ids[0] if len(ids) == 1 else (focus if not ids else None)
        roster = {w["id"]: w for w in ctx.get("my_work_orders", [])}
        question = bool(HYPOTHETICAL.search(text)) or bool(NEGATION.search(text))

        if GREETING.match(text) and len(text) < 40:
            return self._respond("answer", "Hi! Ask me a maintenance question or about one of your work orders.")
        if ROSTER_WORDS.search(text) and not ids:
            lines = [f"{w['id']} {w['title']} - {w['status']} (due {w['dueDate']})" for w in roster.values()]
            return self._respond("answer", "Your work orders: " + "; ".join(lines))

        if not question:
            note = re.search(r"\b(?:add|put|log|leave)\s+(?:a\s+)?note\b[^:]*:\s*(.+)$", text, re.I | re.S) \
                or re.search(r"\bnote (?:on|to|for) [^,:]+?(?: that|:)\s*(.+)$", text, re.I | re.S)
            if NOTE_WORDS.search(text) and note:
                if not target:
                    return self._respond("clarify", "Which work order should the note go on? Please include its ID.")
                return self._call("add_note", {"id": target, "text": note.group(1).strip()})
            if ESCALATE_WORDS.search(text):
                reason = re.search(r"\b(?:because|since|due to|reason:?|:)\s*(.+)$", text, re.I | re.S)
                if not target:
                    return self._respond("clarify", "Which work order should I escalate? Please include its ID.")
                if not reason:
                    return self._respond("clarify", f"What is the reason for escalating {target}? "
                                                    f"Say e.g. \"escalate {target} because ...\".")
                return self._call("escalate", {"id": target, "reason": reason.group(1).strip()})
            statuses = mentioned_statuses(text)
            statuses.discard(next(iter([s for s in statuses if s.value == "Open"]), None))  # type: ignore[arg-type]
            wants_next = bool(NEXT_WORDS.search(text))
            if (statuses or wants_next) and re.search(r"\b(mark|set|move|put|start|begin|complete|close|finish|"
                                                      r"change|update|advance|hold|pause|done)\b", text, re.I):
                if len(ids) > 1 or (not target):
                    return self._respond("clarify", "Which work order do you mean? Please include its ID, "
                                                    "e.g. \"mark WO-003 complete\".")
                if len(statuses) == 1:
                    return self._call("update_status", {"id": target, "status": next(iter(statuses)).value})
                if wants_next and target in roster and roster[target].get("allowedNextStatus"):
                    return self._call("update_status", {"id": target, "status": roster[target]["allowedNextStatus"]})
                return self._respond("clarify", "Which single status should I set?")

        if ids and READ_WORDS.search(text) and not self._kb_topics(text) and not UNSUPPORTED.search(text):
            if len(ids) == 1:
                return self._call("get_work_order", {"id": ids[0]})
            return self._call("get_work_order", {"id": ids[0]})  # first; server clears focus for multi-ID turns
        if not ids and focus and READ_WORDS.search(text) and re.search(r"\b(it|this|that)\b", text, re.I) \
                and not self._kb_topics(text):
            return self._call("get_work_order", {"id": focus})
        return self._kb_answer(text)

    def _kb_topics(self, text: str) -> list[str]:
        return [sid for sid, rx in KB_TOPICS if rx.search(text)]

    def _kb_answer(self, text: str) -> ModelDecision:
        topics = self._kb_topics(text)
        unsupported = UNSUPPORTED.search(text)
        missing: list[str] = []
        if unsupported:
            clause = re.split(r"\band\b|,|\?|\.", text[unsupported.start() - 40 if unsupported.start() > 40 else 0:])
            span = next((c.strip() for c in clause if unsupported.group(0).lower() in c.lower()), unsupported.group(0))
            missing.append(span)
            # "firmware ... reset" -> the reset topic only counts if asked separately
            topics = [t for t in topics if not (t == "kb-1" and re.search(r"lockout after|compressor", text, re.I))]
        if not topics:
            return self._respond("unsupported", "", missing=missing or [text[:200]])
        qtok = set(_content(tokens(text)))
        citations: list[dict[str, str]] = []
        parts: list[str] = []
        for sid in topics[:2]:
            sec = self.kb.get(sid)
            assert sec is not None
            items = _items(sec.body)
            procedural = sid in ("kb-1", "kb-2", "kb-5") and re.search(r"\b(how|steps?|procedure|perform|do i)\b", text, re.I)
            if procedural or sid == "kb-4":
                chosen = items
            else:
                scored = sorted(items, key=lambda it: -len(qtok & set(tokens(it))))
                chosen = [it for it in scored[:2] if qtok & set(tokens(it))] or scored[:1]
            for it in chosen:
                citations.append({"section_id": sid, "quote": it})
            parts.append(f"{sec.heading}: " + " ".join(chosen))
        return self._respond("answer", "\n".join(parts)[:1200], citations, missing)
