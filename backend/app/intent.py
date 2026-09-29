"""IntentGuard: does a model-proposed call match what the technician asked for *this turn*?

This is a consistency check, not a command grammar. The LLM chooses the tool and
arguments; this module refuses proposals that (a) target something the user did
not name or have in focus, (b) change status to something the user's words do not
imply, (c) invent note/escalation text, (d) come from negated or how-to phrasing,
or (e) bundle more than one kind of write. It is deliberately conservative: a
failure asks the user to restate, it never picks a different action.

The hard invariants (ownership, adjacency, schema, one write per turn) live in
``service.py``/``tools.py``/``agent.py`` and do not depend on these heuristics.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from .domain import ErrorCode, Status, ToolResult, next_status
from .tools import AddNoteArgs, EscalateArgs, ParsedCall, UpdateStatusArgs

ID_RE = re.compile(r"\bWO[-\s]?(\d{3})\b", re.IGNORECASE)
QUOTED_RE = re.compile(r"\"[^\"]*\"|“[^”]*”|'[^']{3,}'")
PRONOUN_RE = re.compile(r"\b(it|this|that|this one|that one|the same)\b", re.IGNORECASE)

STATUS_WORDS: dict[Status, re.Pattern[str]] = {
    Status.COMPLETED: re.compile(r"\b(complet\w*|done|finish\w*|close\w*|closing|resolv\w*|wrap(?:ped)? (?:it )?up)\b", re.I),
    Status.ON_HOLD: re.compile(r"\b(on[- ]hold|hold|paus\w*|wait\w*|block\w*|park\w*|suspend\w*)\b", re.I),
    Status.IN_PROGRESS: re.compile(r"\b(in[- ]progress|start\w*|begin\w*|began|progress|working on|commenc\w*|pick(?:ed)? up|kick(?:ed)? off)\b", re.I),
    Status.OPEN: re.compile(r"\b(re-?open\w*|open)\b", re.I),
}
NEXT_WORDS = re.compile(
    r"\b(next (?:status|stage|step|state)|advance\w*|move (?:it |this |wo-\d{3} )?(?:forward|along|ahead|on)|bump)\b", re.I)
NOTE_WORDS = re.compile(r"\b(note|notes|log|record|comment|jot|write down|annotate)\b", re.I)
ESCALATE_WORDS = re.compile(r"\b(escalat\w*|flag(?:ged)? (?:it |this |wo-\d{3} )?(?:for|to)|raise (?:it |this )?(?:with|to))\b", re.I)
STATUS_VERBS = re.compile(r"\b(mark|set|move|change|update|status|put)\b", re.I)
NEGATION = re.compile(
    r"\b(don'?t|do not|never|not yet|no need to|shouldn'?t|should not|stop|cancel|without|avoid)\b(?:\W+\w+){0,4}?\W+"
    r"(?P<verb>mark|set|move|start|complet\w*|close|finish|put|escalat\w*|add|note|log|chang\w*|updat\w*|hold|flag)", re.I)


def _verb_category(verb: str) -> str | None:
    v = verb.lower()
    if v.startswith(("escalat", "flag")):
        return "escalate"
    if v in ("note", "log"):
        return "note"
    if v == "add":
        return None  # ambiguous: treat as negating whatever was asked
    return "status"
HYPOTHETICAL = re.compile(
    r"\b(how (?:do|can|should|would|to)|what (?:happens|if|would)|should i|when (?:should|do|can) i|"
    r"is it (?:ok|okay|safe|possible|allowed)|can i|could i|am i allowed|what does it mean)\b", re.I)

STOPWORDS = frozenset(
    "a an the to of on in for and or but is are was were be been it this that with as at by from "
    "please pls add note escalate escalation reason because since due so wo my our your i we you "
    "has have had do did does can could would should will just also then there here".split())


def extract_ids(text: str) -> list[str]:
    seen: list[str] = []
    for m in ID_RE.finditer(text):
        wid = f"WO-{m.group(1)}"
        if wid not in seen:
            seen.append(wid)
    return seen


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text.lower().replace("’", "'"))


def _content(toks: list[str]) -> list[str]:
    return [t for t in toks if t not in STOPWORDS and (len(t) > 1 or t.isdigit())]


def _match(tok: str, pool: set[str]) -> bool:
    if tok in pool:
        return True
    if len(tok) >= 5:  # tolerate inflection: replaced/replacing, wiring/wires
        return any(len(p) >= 5 and p[:5] == tok[:5] for p in pool)
    return False


def grounded_ratio(payload: str, message: str) -> float:
    ptoks = _content(tokens(payload))
    if not ptoks:
        return 0.0
    pool = set(tokens(message))
    return sum(_match(t, pool) for t in ptoks) / len(ptoks)


def strip_payload(message: str, payload: str | None) -> str:
    """Remove the payload words so words *inside* a note never count as commands."""
    text = QUOTED_RE.sub(" ", message)
    if not payload:
        return text
    lower = message.lower()
    idx = lower.find(payload.lower())
    if idx >= 0:
        return QUOTED_RE.sub(" ", message[:idx] + " " + message[idx + len(payload):])
    remove = Counter(tokens(payload))
    kept: list[str] = []
    for t in tokens(text):
        if remove[t] > 0:
            remove[t] -= 1
        else:
            kept.append(t)
    return " ".join(kept)


def mentioned_statuses(text: str) -> set[Status]:
    return {s for s, rx in STATUS_WORDS.items() if rx.search(text)}


# A message made only of these words plus one work-order ID is a plain lookup ("show WO-003", "what's the
# status of WO-005?"). After the model chooses get_work_order for exactly that ID, the server renders the
# result from the database row instead of asking the model to restate it. Anything else (a question, an
# action word, a negation) keeps the normal model turn.
LOOKUP_WORDS = frozenset(
    "show open get view display pull bring look up see check find give me the a an this that work order wo "
    "please pls can could would you i let let's lets for of on about at what what's whats is status details "
    "detail info information current card".split())


def is_plain_lookup(message: str, explicit_ids: list[str]) -> bool:
    if len(explicit_ids) != 1:
        return False
    return all(t in LOOKUP_WORDS for t in tokens(ID_RE.sub(" ", message)))


def action_categories(text: str) -> set[str]:
    cats = set()
    if NOTE_WORDS.search(text):
        cats.add("note")
    if ESCALATE_WORDS.search(text):
        cats.add("escalate")
    if ((mentioned_statuses(text) - {Status.OPEN}) or NEXT_WORDS.search(text)
            or re.search(r"\bstatus\b|\bre-?open", text, re.I)):
        cats.add("status")
    return cats


@dataclass
class TurnFacts:
    message: str
    explicit_ids: list[str]
    focus_id: str | None  # focus established by an earlier turn or an explicit ID in this one
    focus_from_earlier_turn: bool
    roster_ids: set[str] = field(default_factory=set)
    intent_text: str = ""  # message, optionally prefixed by a pending clarification's original request

    def __post_init__(self) -> None:
        if not self.intent_text:
            self.intent_text = self.message


def clarify(message: str) -> ToolResult:
    return ToolResult.fail(ErrorCode.CLARIFICATION_REQUIRED, message)


def mismatch(message: str) -> ToolResult:
    return ToolResult.fail(ErrorCode.INTENT_MISMATCH, message)


class IntentGuard:
    def __init__(self, payload_threshold: float = 0.75):
        self.payload_threshold = payload_threshold

    @staticmethod
    def _payload(call: ParsedCall) -> str | None:
        if isinstance(call.args, AddNoteArgs):
            return call.args.text
        if isinstance(call.args, EscalateArgs):
            return call.args.reason
        return None

    # ---- target binding ------------------------------------------------------------------
    def check_binding(self, call: ParsedCall, facts: TurnFacts) -> ToolResult | None:
        target = call.target_id
        if not call.is_mutation:
            allowed = set(facts.explicit_ids) | facts.roster_ids | ({facts.focus_id} if facts.focus_id else set())
            if target not in allowed:
                return mismatch(f"I can only look up work orders you mention or that are assigned to you; {target} isn't one of them.")
            return None

        ids = extract_ids(strip_payload(facts.message, self._payload(call)))
        if len(ids) > 1:
            return clarify(f"Your message mentions {', '.join(ids)}. Which single work order should I change? "
                           f"Send one action per message, e.g. \"mark {ids[0]} complete\".")
        if len(ids) == 1:
            if target != ids[0]:
                return mismatch(f"You asked about {ids[0]}, but the proposed change targeted {target}. Nothing was changed.")
            return None
        if not facts.focus_id or not facts.focus_from_earlier_turn:
            return clarify("Which work order do you mean? Please include its ID, e.g. \"mark WO-003 complete\".")
        if target != facts.focus_id:
            return mismatch(f"We were discussing {facts.focus_id}, but the proposed change targeted {target}. Nothing was changed.")
        return None

    # ---- action consistency -----------------------------------------------------------------
    def check_intent(self, call: ParsedCall, facts: TurnFacts, current: Status | None) -> ToolResult | None:
        payload = self._payload(call)
        text = strip_payload(facts.intent_text, payload)

        wanted = {"update_status": "status", "add_note": "note", "escalate": "escalate"}[call.name]
        for neg in list(NEGATION.finditer(text)):
            if _verb_category(neg.group("verb")) in (wanted, None):
                return clarify("Your message reads as *not* wanting this change, so I didn't change anything. "
                               "If you do want it, say it directly, e.g. \"mark WO-003 complete\".")
            text = text.replace(neg.group(0), " ")  # "never mind the note" is not a second request
        if HYPOTHETICAL.search(text):
            return clarify("That sounds like a question rather than a request, so I didn't change anything. "
                           "To make the change, say it directly, e.g. \"put WO-001 on hold\".")

        cats = action_categories(text)
        if wanted not in cats:
            return mismatch("I couldn't find that action in your message, so nothing was changed. "
                            "Tell me exactly what to do, e.g. \"add a note to WO-002: filter replaced\".")
        if len(cats) > 1:
            return ToolResult.fail(ErrorCode.MULTIPLE_ACTIONS,
                                   "I can make one change per message. Please send these as separate requests "
                                   f"({' / '.join(sorted(cats))}). Nothing was changed.")

        if isinstance(call.args, UpdateStatusArgs):
            requested = Status(call.args.status)
            said = mentioned_statuses(text)
            if requested is not Status.OPEN:
                said.discard(Status.OPEN)  # "the panel is open" is not a status request
            if said - {requested} and requested in said:
                return clarify(f"Your message mentions more than one status ({', '.join(s.value for s in sorted(said, key=list(Status).index))}). "
                               "Tell me the single status to set. Nothing was changed.")
            if requested in said:
                return None
            if NEXT_WORDS.search(text) and current is not None and next_status(current) == requested:
                return None
            return mismatch(f"You didn't ask for {requested.value}, so I didn't change anything. "
                            "Status changes must be requested explicitly, one step at a time.")

        assert payload is not None
        if grounded_ratio(payload, facts.message) < self.payload_threshold:
            kind = "note text" if call.name == "add_note" else "reason"
            return clarify(f"Please include the exact {kind} in your message, e.g. "
                           + ("\"add a note to WO-002: filter replaced\"." if call.name == "add_note"
                              else "\"escalate WO-006 because exposed wiring was found\".")
                           + " Nothing was changed.")
        return None
