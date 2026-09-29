"""ChatService: one bounded, auditable turn.

    reserve request id (idempotency)
      -> resolve focus from the technician's own text (deterministic)
      -> model proposes a call            (<= MAX_MODEL_CALLS, one transient retry counted)
      -> ToolDispatcher: registry + strict schema
      -> IntentGuard: target binding + action consistency
      -> WorkOrderService: ownership + legal transition, inside BEGIN IMMEDIATE
      -> deterministic receipt  |  AnswerVerifier for `respond`
      -> persist messages + session + request result (same transaction as any write)

A mutation — accepted or refused — ends the turn. There is no repair loop.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from .config import Settings
from .db import Database, dumps, fetch_work_order, utcnow
from .domain import ErrorCode, Status, ToolResult
from .grounding import AnswerVerifier, Evidence, VerifiedReply
from .intent import IntentGuard, TurnFacts, action_categories, is_plain_lookup, tokens
from .knowledge import KnowledgeBase
from .llm.base import ModelClient, ModelError, ModelMessage
from .memory import ContextBuilder, SessionState, SessionStore, resolve_focus
from .prompts.registry import PromptRegistry
from .service import WorkOrderService, dump_result
from .tools import MUTATING_TOOLS, RESPOND_TOOL, AddNoteArgs, EscalateArgs, ParsedCall, ToolDispatcher, UpdateStatusArgs, tool_specs

log = logging.getLogger("fta.turn")

NO_VERIFIED_REPLY = ("I couldn't produce a verified reply to that. Please rephrase, or ask about a specific "
                     "work order (e.g. \"show WO-003\").")
BUSY = "Another message in this chat is still being processed. Wait for it to finish, then send again."
INTERRUPTED = "That request was interrupted before it finished, and nothing was changed. Please send it again."


class TurnError(Exception):
    def __init__(self, code: ErrorCode, message: str, http_status: int, retryable: bool):
        super().__init__(message)
        self.code, self.message, self.http_status, self.retryable = code, message, http_status, retryable


@dataclass
class Counters:
    model_calls: int = 0
    tool_calls: int = 0
    retries: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    codes: list[str] = field(default_factory=list)


@dataclass
class TurnOutcome:
    outcome: str  # answered | acted | refused | clarification | error
    text: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    cards: list[dict[str, Any]] = field(default_factory=list)
    action: dict[str, Any] | None = None
    missing: list[str] = field(default_factory=list)
    verified: bool = True
    kind: str = ""


def lookup_text(wo: dict[str, Any]) -> str:
    """One line rendered from the database row; the card beside it shows the rest."""
    nxt = wo.get("allowedNextStatus")
    after = f"The next allowed status is {nxt}." if nxt else "No further status changes are allowed."
    return f"{wo['id']} is {wo['status']}. {after}"


def _hash(message: str) -> str:
    return hashlib.sha256(message.encode("utf-8")).hexdigest()


class ChatService:
    def __init__(self, settings: Settings, db: Database, kb: KnowledgeBase, model: ModelClient,
                 prompts: PromptRegistry | None = None):
        self.settings = settings
        self.db = db
        self.kb = kb
        self.model = model
        self.prompts = prompts or PromptRegistry()
        self.principal = db.principal()
        self.service = WorkOrderService(self.principal["id"])
        self.dispatcher = ToolDispatcher(settings.max_note_chars, settings.max_reason_chars)
        self.guard = IntentGuard()
        self.verifier = AnswerVerifier(kb)
        self.context = ContextBuilder(settings.history_messages, settings.history_char_budget)
        self.tools = tool_specs(settings.max_note_chars, settings.max_reason_chars)
        self.system_prompt = self.prompts.system(kb.prompt_block(), kb.sha256)
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()
        self._model_slots = threading.BoundedSemaphore(settings.model_concurrency)

    # ---- sessions & reads ---------------------------------------------------------------------
    def create_session(self, browser_id: str) -> dict[str, Any]:
        with self.db.transaction() as tx:
            st = SessionStore.create(tx, self.principal["id"], browser_id)
        return {"session_id": st.id, "messages": [], "state": st.public()}

    def session_view(self, session_id: str, browser_id: str) -> dict[str, Any] | None:
        with self.db.read() as conn:
            st = SessionStore.load(conn, session_id, self.principal["id"], browser_id)
            if st is None:
                return None
            return {"session_id": st.id, "messages": SessionStore.messages(conn, st.id), "state": st.public()}

    def request_view(self, session_id: str, browser_id: str, request_id: str) -> tuple[int, dict[str, Any]] | None:
        with self.db.read() as conn:
            if SessionStore.load(conn, session_id, self.principal["id"], browser_id) is None:
                return None
            row = conn.execute("SELECT state, response_json FROM requests WHERE user_id=? AND session_id=? AND request_id=?",
                               (self.principal["id"], session_id, request_id)).fetchone()
        if row is None:
            return None
        if row["state"] == "processing":
            return 202, {"request_id": request_id, "status": "pending"}
        if row["state"] == "interrupted":
            return 200, self._interrupted_body(session_id, request_id)
        return 200, json.loads(row["response_json"])

    def roster(self) -> list[dict[str, Any]]:
        with self.db.read() as conn:
            return self.service.list_own(conn)

    def _interrupted_body(self, session_id: str, request_id: str) -> dict[str, Any]:
        return {"request_id": request_id, "session_id": session_id, "outcome": "error",
                "code": ErrorCode.INTERNAL_ERROR.value, "message": INTERRUPTED, "retryable": False}

    def _try_lock_session(self, session_id: str) -> bool:
        """Acquire and (later) drop per-session locks under one guard, so the dict never
        grows without bound and no two turns can hold different locks for one session."""
        with self._locks_guard:
            lock = self._locks.setdefault(session_id, threading.Lock())
            return lock.acquire(blocking=False)

    def _unlock_session(self, session_id: str) -> None:
        with self._locks_guard:
            lock = self._locks.get(session_id)
            if lock is not None:
                lock.release()
                del self._locks[session_id]

    # ---- entry point ------------------------------------------------------------------------------
    def handle_message(self, session_id: str, browser_id: str, request_id: str, message: str) -> tuple[int, dict[str, Any]]:
        user_id = self.principal["id"]
        input_hash = _hash(message)
        with self.db.transaction() as tx:
            st = SessionStore.load(tx, session_id, user_id, browser_id)
            if st is None:
                return 404, {"detail": "Session not found."}
            row = tx.execute("SELECT input_hash, state, response_json FROM requests WHERE user_id=? AND session_id=? AND request_id=?",
                             (user_id, session_id, request_id)).fetchone()
            if row is not None:
                if row["input_hash"] != input_hash:
                    return 409, {"detail": "This request ID was already used for a different message.",
                                 "code": ErrorCode.CONFLICT.value}
                if row["state"] == "completed":
                    return 200, json.loads(row["response_json"])
                if row["state"] == "processing":
                    return 202, {"request_id": request_id, "status": "pending"}
                return 200, self._interrupted_body(session_id, request_id)
            now = utcnow()
            tx.execute("INSERT INTO requests VALUES (?,?,?,?,?,?,?,?)",
                       (user_id, session_id, request_id, input_hash, "processing", None, now, now))

        if not self._try_lock_session(session_id):
            self._release_request(session_id, request_id)
            return 409, {"detail": BUSY, "code": ErrorCode.CONFLICT.value}
        counters = Counters()
        started = time.monotonic()
        outcome = "error"
        try:
            body = self._turn(st, request_id, message, counters, started)
            outcome = body["outcome"]
            return 200, body
        except TurnError as exc:
            self._release_request(session_id, request_id)  # nothing was written: same ID may retry
            counters.codes.append(exc.code.value)
            return exc.http_status, {"request_id": request_id, "session_id": session_id, "outcome": "error",
                                     "code": exc.code.value, "message": exc.message, "retryable": exc.retryable}
        except Exception:
            log.exception("turn_failed", extra={"request_id": request_id})
            self._release_request(session_id, request_id)
            return 500, {"request_id": request_id, "session_id": session_id, "outcome": "error",
                         "code": ErrorCode.INTERNAL_ERROR.value,
                         "message": "Something went wrong on the server. Nothing was changed.", "retryable": True}
        finally:
            self._unlock_session(session_id)
            log.info("turn", extra={
                "request_id": request_id, "session_id": session_id, "outcome": outcome,
                "model_calls": counters.model_calls, "tool_calls": counters.tool_calls,
                "retries": counters.retries, "codes": counters.codes,
                "input_tokens": counters.input_tokens, "output_tokens": counters.output_tokens,
                "latency_ms": int((time.monotonic() - started) * 1000), "provider": self.model.provider,
            })

    def _release_request(self, session_id: str, request_id: str) -> None:
        with self.db.transaction() as tx:
            tx.execute("DELETE FROM requests WHERE user_id=? AND session_id=? AND request_id=? AND state='processing'",
                       (self.principal["id"], session_id, request_id))

    # ---- the turn -----------------------------------------------------------------------------------
    def _turn(self, st: SessionState, request_id: str, message: str, counters: Counters, started: float) -> dict[str, Any]:
        deadline = started + self.settings.turn_timeout_seconds
        with self.db.read() as conn:
            roster = self.service.list_own(conn)
            history = SessionStore.messages(conn, st.id, limit=60)
        owned = {w["id"] for w in roster}
        res = resolve_focus(st, message, owned)

        intent_text = message
        pending = st.pending
        if (pending and pending.get("tool") == "update_status" and len(res.explicit_ids) == 1
                and not action_categories(message) and len(tokens(message)) <= 8):
            intent_text = f"{pending.get('source', '')} {message}"  # "which one?" -> "WO-003"
        facts = TurnFacts(message, res.explicit_ids, res.focus_id, res.focus_from_earlier_turn, owned, intent_text)

        new_state = SessionState(st.id, st.user_id, st.browser_id, res.focus_id, list(res.candidates), None)
        hist_msgs, _dropped = self.context.history(history)
        msgs: list[ModelMessage] = [*hist_msgs, self.context.server_context(self.principal, res, roster, pending),
                                    self.context.user_message(message)]
        evidence = Evidence(message, [], roster, res.focus_id)
        read_ids: list[str] = []
        cards: list[dict[str, Any]] = []

        def done(out: TurnOutcome) -> dict[str, Any]:
            self._update_focus_after_reads(new_state, res.explicit_ids, read_ids)
            with self.db.transaction() as tx:
                return self._complete(tx, new_state, request_id, message, out, counters, started)

        while counters.model_calls < self.settings.max_model_calls_per_turn:
            decision = self._generate(msgs, deadline, counters)
            calls = list(decision.tool_calls)
            if not calls:
                counters.codes.append("NO_TOOL_CALL")
                return done(TurnOutcome("error", NO_VERIFIED_REPLY, cards=cards, verified=False))
            if sum(c.name in MUTATING_TOOLS for c in calls) > 1:
                counters.codes.append(ErrorCode.MULTIPLE_ACTIONS.value)
                return done(TurnOutcome("refused", "I can make one change per message. Please send each change "
                                        "separately. Nothing was changed.", cards=cards,
                                        action={"tool": None, "code": ErrorCode.MULTIPLE_ACTIONS.value, "ok": False}))
            business = [c for c in calls if c.name != RESPOND_TOOL]
            to_run = business if business else calls[:1]  # a respond sent alongside reads was written blind
            msgs.append(ModelMessage(role="assistant", content=decision.text, tool_calls=tuple(to_run)))

            for call in to_run:
                counters.tool_calls += 1
                if counters.tool_calls > self.settings.max_tool_calls_per_turn:
                    counters.codes.append(ErrorCode.LIMIT_REACHED.value)
                    return done(TurnOutcome("error", "I couldn't finish that within my step limit. Try a narrower "
                                            "request, e.g. one work order at a time.", cards=cards, verified=False))
                parsed = self.dispatcher.parse(call.id, call.name, call.arguments)
                if isinstance(parsed, ToolResult):
                    counters.codes.append(parsed.code.value)
                    if call.name == RESPOND_TOOL:
                        return done(TurnOutcome("error", NO_VERIFIED_REPLY, cards=cards, verified=False))
                    text = parsed.message if "Nothing was" in parsed.message else f"{parsed.message} Nothing was changed."
                    return done(TurnOutcome("refused", text, cards=cards,
                                            action={"tool": call.name[:40], "code": parsed.code.value, "ok": False}))
                if parsed.name == RESPOND_TOOL:
                    return done(self._answer(parsed, evidence, cards, message, new_state))

                binding = self.guard.check_binding(parsed, facts)
                if binding is not None:
                    counters.codes.append(binding.code.value)
                    if binding.code == ErrorCode.CLARIFICATION_REQUIRED and isinstance(parsed.args, UpdateStatusArgs):
                        new_state.pending = {"tool": "update_status", "source": message[:500], "question": binding.message}
                    return done(self._refusal(binding, parsed, cards))

                if not parsed.is_mutation:
                    with self.db.read() as conn:
                        result = self.service.get(conn, parsed.target_id or "")
                    counters.codes.append(result.code.value)
                    if result.ok and result.data:
                        cards.append(result.data)
                        evidence.tool_data.append(result.data)
                        read_ids.append(result.data["id"])
                    else:
                        evidence.tool_data.append({"id": parsed.target_id, "available": False})
                    if (len(to_run) == 1 and res.explicit_ids == [parsed.target_id]
                            and is_plain_lookup(message, res.explicit_ids)):
                        # The model chose the read; restating the row would only cost a second call (D65).
                        counters.codes.append("LOOKUP_RENDERED")
                        if result.ok and result.data:
                            return done(TurnOutcome("answered", lookup_text(result.data), cards=cards, kind="lookup"))
                        return done(TurnOutcome("refused", self.verifier.refusal(evidence), cards=cards, kind="refuse"))
                    msgs.append(ModelMessage(role="tool", content=dump_result(result), tool_call_id=call.id,
                                             tool_name=call.name))
                    continue

                return self._mutate(parsed, facts, new_state, request_id, message, cards, counters, started)

        counters.codes.append(ErrorCode.LIMIT_REACHED.value)
        return done(TurnOutcome("error", "I couldn't finish that within my step limit. Try a narrower request.",
                                cards=cards, verified=False))

    def _generate(self, msgs: list[ModelMessage], deadline: float, counters: Counters):
        while True:
            if counters.model_calls >= self.settings.max_model_calls_per_turn:
                raise TurnError(ErrorCode.LIMIT_REACHED, "The model step limit was reached.", 503, True)
            remaining = deadline - time.monotonic()
            if remaining <= 1:
                raise TurnError(ErrorCode.PROVIDER_UNAVAILABLE, "The assistant took too long. Nothing was changed; "
                                "please try again.", 503, True)
            counters.model_calls += 1
            if not self._model_slots.acquire(timeout=min(remaining, 10)):
                raise TurnError(ErrorCode.PROVIDER_UNAVAILABLE, "The assistant is busy. Please try again.", 503, True)
            try:
                decision = self.model.generate(self.system_prompt, msgs, self.tools,
                                               max_output_tokens=self.settings.max_output_tokens,
                                               timeout=min(self.settings.model_timeout_seconds, remaining))
                counters.input_tokens += decision.usage.input_tokens or 0
                counters.output_tokens += decision.usage.output_tokens or 0
                return decision
            except ModelError as exc:
                log.warning("model_error", extra={"kind": exc.kind, "transient": exc.transient, "error": str(exc)})
                if exc.transient and counters.retries == 0 and counters.model_calls < self.settings.max_model_calls_per_turn:
                    counters.retries += 1
                    continue
                if exc.kind == "config":
                    raise TurnError(ErrorCode.PROVIDER_UNAVAILABLE, "The model provider rejected the request "
                                    "(server configuration). Nothing was changed.", 503, False) from exc
                raise TurnError(ErrorCode.PROVIDER_UNAVAILABLE, "The model provider is unavailable right now. "
                                "Nothing was changed; please try again.", 503, True) from exc
            finally:
                self._model_slots.release()

    # ---- endings ------------------------------------------------------------------------------------
    @staticmethod
    def _refusal(result: ToolResult, parsed: ParsedCall, cards: list[dict[str, Any]]) -> TurnOutcome:
        outcome = "clarification" if result.code == ErrorCode.CLARIFICATION_REQUIRED else "refused"
        return TurnOutcome(outcome, result.message, cards=cards,
                           action={"tool": parsed.name, "work_order_id": parsed.target_id,
                                   "code": result.code.value, "ok": False})

    def _answer(self, parsed: ParsedCall, evidence: Evidence, cards: list[dict[str, Any]], message: str,
                new_state: SessionState) -> TurnOutcome:
        v: VerifiedReply = self.verifier.verify(parsed.args, evidence)  # type: ignore[arg-type]
        if v.issues:
            log.info("answer_fallback", extra={"issues": v.issues[:5]})
        text = v.text
        if v.missing and v.kind in ("partial", "fallback", "unsupported"):
            text += "\n\nNot covered by the knowledge base: " + "; ".join(v.missing) + "."
        if v.kind == "clarify" and action_categories(message) == {"status"} and not evidence.focus_id:
            new_state.pending = {"tool": "update_status", "source": message[:500], "question": text}
        outcome = {"clarify": "clarification", "refuse": "refused"}.get(v.kind, "answered")
        return TurnOutcome(outcome, text, v.sources, cards, None, v.missing, v.verified, v.kind)

    def _mutate(self, parsed: ParsedCall, facts: TurnFacts, new_state: SessionState, request_id: str,
                message: str, cards: list[dict[str, Any]], counters: Counters, started: float) -> dict[str, Any]:
        target = parsed.target_id or ""
        with self.db.read() as conn:
            wo = fetch_work_order(conn, target)
        owned = wo is not None and wo.assigned_tech == self.principal["id"]
        if owned:  # unowned targets go straight to the service, which refuses and audits
            problem = self.guard.check_intent(parsed, facts, wo.status if wo else None)
            if problem is not None:
                counters.codes.append(problem.code.value)
                self._update_focus_after_reads(new_state, facts.explicit_ids, [])
                with self.db.transaction() as tx:
                    return self._complete(tx, new_state, request_id, message,
                                          self._refusal(problem, parsed, cards), counters, started)

        with self.db.transaction() as tx:
            args = parsed.args
            if isinstance(args, UpdateStatusArgs):
                result = self.service.update_status(tx, target, args.status, request_id)
            elif isinstance(args, AddNoteArgs):
                result = self.service.add_note(tx, target, args.text, request_id)
            elif isinstance(args, EscalateArgs):
                result = self.service.escalate(tx, target, args.reason, request_id)
            else:  # pragma: no cover - registry guarantees this
                raise AssertionError(parsed.name)
            counters.codes.append(result.code.value)
            if result.ok:
                new_state.focus_id, new_state.candidates = target, []
                with_card = self.service.get(tx, target)
                cards = [c for c in cards if c.get("id") != target] + ([with_card.data] if with_card.data else [])
            elif result.code == ErrorCode.ACCESS_DENIED_OR_NOT_FOUND:
                new_state.focus_id, new_state.candidates = None, []
            action = {"tool": parsed.name, "work_order_id": target, "code": result.code.value, "ok": result.ok}
            if result.data:
                action.update({k: result.data[k] for k in ("version", "status", "previousStatus", "allowedNextStatus",
                                                           "text", "reason", "at") if k in result.data})
            out = TurnOutcome("acted" if result.ok else "refused", result.message, cards=cards, action=action)
            return self._complete(tx, new_state, request_id, message, out, counters, started)

    @staticmethod
    def _update_focus_after_reads(state: SessionState, explicit_ids: list[str], read_ids: list[str]) -> None:
        distinct = list(dict.fromkeys(read_ids))
        if explicit_ids or not distinct:
            return
        if len(distinct) == 1:
            state.focus_id, state.candidates = distinct[0], []
        else:
            state.focus_id, state.candidates = None, distinct

    def _complete(self, tx, state: SessionState, request_id: str, message: str, out: TurnOutcome,
                  counters: Counters, started: float) -> dict[str, Any]:
        user_mid = SessionStore.append_message(tx, state.id, request_id, "user", message, {})
        payload = {"sources": out.sources, "cards": out.cards, "action": out.action, "missing": out.missing,
                   "verified": out.verified, "outcome": out.outcome}
        asst_mid = SessionStore.append_message(tx, state.id, request_id, "assistant", out.text, payload)
        SessionStore.save(tx, state)
        body = {
            "request_id": request_id,
            "session_id": state.id,
            "outcome": out.outcome,
            "messages": [
                {"id": user_mid, "role": "user", "text": message},
                {"id": asst_mid, "role": "assistant", "text": out.text, **payload},
            ],
            "state": state.public(),
            "action": out.action,
            "retryable": False,
            "meta": {"model_calls": counters.model_calls, "tool_calls": counters.tool_calls,
                     "latency_ms": int((time.monotonic() - started) * 1000), "provider": self.model.provider,
                     "is_llm": self.model.is_llm},
        }
        tx.execute("UPDATE requests SET state='completed', response_json=?, updated_at=? "
                   "WHERE user_id=? AND session_id=? AND request_id=?",
                   (dumps(body), utcnow(), self.principal["id"], state.id, request_id))
        return body


__all__ = ["ChatService", "TurnError", "Status"]
