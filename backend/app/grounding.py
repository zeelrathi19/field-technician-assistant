"""AnswerVerifier: nothing reaches the technician as fact unless code can trace it.

The model may *phrase* an answer, but:
  * every citation must be a verbatim quote from the cited approved section;
  * every number (digits or number words), date, work-order ID and status name in
    the answer must appear in the evidence (cited sections, this turn's tool
    results, the technician's own roster, or the technician's own message);
  * an answer with maintenance content but no evidence is replaced by a fixed
    abstention;
  * a count of the technician's work orders ("7 work orders") must equal a count the
    server derives from their own roster; the count licenses no other number;
  * a refusal's facts are always server text. The model may phrase one opening sentence
    for it, shown only if it passes `_refusal_lead_ok` (a denial, no IDs/numbers/names/
    ownership claims/unasked maintenance terms); an ID refusal is fully fixed.
Any failure falls back to deterministic rendering (whole approved sections, or the
fixed abstention). The verifier proves provenance, not relevance.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from .intent import STOPWORDS, tokens
from .knowledge import KnowledgeBase, normalize
from .tools import RespondArgs

ABSTAIN = "The knowledge base doesn't cover that, so I can't give you an answer or procedure for it. I won't guess."
UNVERIFIED = ("I couldn't verify a summary against the approved sources, so here is the exact knowledge-base text instead.")
GENERIC_CLARIFY = "Could you tell me which work order (for example WO-003) and what you'd like me to do?"
# Refusals are fixed server text. Unowned and missing IDs get the service's public wording, so
# nothing distinguishes "another technician's order" from "no such order".
NOT_AVAILABLE = ("Work order {id} is not available to you. You can only view or act on work orders "
                 "assigned to you.")
SCOPE_REFUSAL = ("I can only see the work orders assigned to you, so I can't show other technicians' work "
                 "orders or say who they're assigned to.")
MAX_REFUSAL_LEAD_CHARS = 240
DENIAL_CUE = re.compile(r"\b(can't|cannot|can not|unable|not able|only|don't have|do not have|not available)\b", re.I)
# Words that would assert who owns what, or whether something exists. The model cannot know either.
OWNERSHIP_CLAIM = re.compile(
    r"\b(belongs?|belonging|owned|owns?|handled|handles|handling|exists?|existing|no such|"
    r"(?:is|are|was|were)\s+(?:assigned|given|allocated)\s+to\s+(?!you\b))", re.I)
ALWAYS_CAPITALISED = {"i", "i'm", "i've", "i'll", "i'd"}
# A sentence may open with one of these (or a function word, or the technician's own word); any other
# capitalised opener could be a name, so the lead is rejected.
SENTENCE_STARTERS = {"sorry", "unfortunately", "those", "these", "other", "work", "details", "information",
                     "only", "however", "that's", "it's", "there's", "access", "assignments"}
ROSTER_LINE = "You have {n} work order{s} assigned to you, listed under My work orders."
CAPABILITIES = ("I can answer questions from the field-service knowledge base, and look up, update status, add notes "
                "to, or escalate the work orders assigned to you.")

NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7",
    "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12", "fifteen": "15", "twenty": "20",
    "thirty": "30", "forty": "40", "fifty": "50", "sixty": "60", "seventy": "70", "eighty": "80",
    "ninety": "90", "hundred": "100", "thousand": "1000", "half": "0.5", "once": "1", "twice": "2",
    "single": "1", "double": "2", "triple": "3", "dozen": "12",
}
# "once"/"single" are too common in ordinary prose to be treated as numeric claims unless digits back them.
SOFT_NUMBER_WORDS = {"once", "single", "one", "half", "double"}

STATUS_NAMES = ("In Progress", "On Hold", "Completed")
DOMAIN_TERMS = re.compile(
    r"\b(reset|filter|warrant\w*|lock\w*|tag\w*|torque|pressure|volt\w*|amp\w*|refrigerant|wiring|wire|compressor|"
    r"firmware|breaker|fuse|thermostat|coolant|psi|nm|install\w*|replace\w*|escalat\w*|led|panel|disconnect|"
    r"airflow|blower|serial|labor|labour|parts?|safety|hazard|procedure|step)\b", re.I)
ID_RE = re.compile(r"\bWO-\d{3}\b")
DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
NUM_RE = re.compile(r"(?<![\w-])\d+(?:[.,]\d+)?(?![\w-])")
# Answers must be plain text: no raw HTML/markdown links/images reach the UI.
MARKUP_RE = re.compile(r"<\s*/?\s*[a-z][^>]*>|!\[|\]\(", re.I)
SAFETY_COMPANION = {"kb-1": "kb-2", "kb-5": "kb-2"}
# Asset / model codes such as CU-4400 or AF-200 (digits after '-' are not caught by NUM_RE).
ASSET_RE = re.compile(r"\b(?!WO-)[A-Z]{2,}-\d{2,}\b")
# Status claims ("WO-003 is done") — synonyms map to canonical statuses.
STATUS_WORDS = {
    "Completed": r"complet(?:e|ed)|done|finished|closed|resolved",
    "On Hold": r"on[- ]hold|paused",
    "In Progress": r"in[- ]progress|started|underway",
    "Open": r"open|reopened",
}
_STATUS_ALT = "|".join(f"(?P<s{i}>{rx})" for i, rx in enumerate(STATUS_WORDS.values()))
STATUS_CLAIM = re.compile(
    r"\b(?:is|are|was|were|has been|have been|now|already|marked(?: as)?|set to|moved to|changed to|updated to)"
    r"\s+(?:now\s+|already\s+|currently\s+|still\s+|been\s+)?(?:status\s+)?(?:" + _STATUS_ALT + r")\b", re.I)
# "7 work orders", "seven open work orders", "3 orders on hold" — a count of the technician's orders.
_NUM_TOKEN = r"\d+|" + "|".join(sorted(("zero one two three four five six seven eight nine ten eleven twelve "
                                         "fifteen twenty").split(), key=len, reverse=True))
COUNT_CLAIM = re.compile(
    r"\b(?P<n>" + _NUM_TOKEN + r")\s+(?:(?:assigned|active|open|total|current|other|of\s+your|in[- ]progress|"
    r"on[- ]hold|completed)\s+){0,3}(?:work\s+)?orders?\b", re.I)
HEDGE = re.compile(r"\b(next|allowed|only|can|could|would|should|cannot|can't|must|if|once|after|before|until|to be)\b", re.I)
# The respond tool never follows a write (a write ends the turn), so any claim of having acted is false.
ACTION_CLAIM = re.compile(
    r"\b(?:i|we)(?:'ve| have)?\s+(?:just\s+|now\s+|successfully\s+|already\s+)?"
    r"(?:marked|updated|changed|set|moved|added|logged|recorded|escalated|flagged|completed|closed|started|put|saved)\b"
    r"|\bhas been (?:marked|updated|changed|set|moved|escalated|flagged|added|logged|recorded|saved)\b"
    r"|\b(?:note|escalation|status change) (?:has been |was )?(?:added|recorded|logged|created|saved|applied)\b", re.I)


@dataclass
class Evidence:
    user_message: str
    tool_data: list[dict[str, Any]] = field(default_factory=list)
    roster: list[dict[str, Any]] = field(default_factory=list)
    focus_id: str | None = None

    def roster_counts(self) -> set[str]:
        """Counts the server can prove from the technician's own roster: total and per status."""
        counts = {len(self.roster)}
        for status in {w.get("status") for w in self.roster}:
            counts.add(sum(w.get("status") == status for w in self.roster))
        return {str(n) for n in counts}

    def text(self, include_user: bool = True) -> str:
        parts = [json.dumps(self.tool_data), json.dumps(self.roster), self.focus_id or ""]
        if include_user:  # the user's own words may be echoed in questions, never asserted as facts
            parts.append(self.user_message)
        return " ".join(parts)


@dataclass
class VerifiedReply:
    kind: str  # answer | partial | unsupported | clarify | refuse | fallback | smalltalk
    text: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    @property
    def verified(self) -> bool:
        return not self.issues


def _numbers(text: str) -> set[str]:
    nums = {n.replace(",", "") for n in NUM_RE.findall(text)}
    for tok in tokens(text):
        if tok in NUMBER_WORDS and tok not in SOFT_NUMBER_WORDS:
            nums.add(NUMBER_WORDS[tok])
    return nums


class AnswerVerifier:
    def __init__(self, kb: KnowledgeBase):
        self.kb = kb

    def _sources(self, cited: dict[str, list[str]]) -> list[dict[str, Any]]:
        order = [s.id for s in self.kb.sections]
        ids = sorted(cited, key=order.index)
        out = []
        for sid in ids:
            src = self.kb.get(sid).to_source()  # type: ignore[union-attr]
            src["quotes"] = cited[sid]
            src["related"] = False
            out.append(src)
        for sid in ids:  # procedures on powered equipment always carry the lockout section
            comp = SAFETY_COMPANION.get(sid)
            if comp and comp not in cited and all(s["section_id"] != comp for s in out):
                src = self.kb.get(comp).to_source()  # type: ignore[union-attr]
                src["quotes"], src["related"] = [], True
                out.append(src)
        return out

    @staticmethod
    def _known_statuses(evidence: "Evidence | None") -> dict[str, str]:
        known: dict[str, str] = {}
        if evidence is None:
            return known
        for row in [*evidence.roster, *evidence.tool_data]:  # tool results (fresher) override the roster
            if isinstance(row, dict) and row.get("id") and row.get("status"):
                known[row["id"]] = row["status"]
        return known

    def _status_claims(self, text: str, evidence: "Evidence | None") -> list[str]:
        known = self._known_statuses(evidence)
        issues = []
        all_ids = ID_RE.findall(text)
        for sentence in re.split(r"(?<=[.!?;\n])\s+", text):
            ids = ID_RE.findall(sentence) or (all_ids[:1] if len(set(all_ids)) == 1 else [])
            if len(set(ids)) != 1 or ids[0] not in known:
                continue
            wid = ids[0]
            for m in STATUS_CLAIM.finditer(sentence):
                prefix = sentence[max(0, m.start() - 30):m.start()]
                if HEDGE.search(prefix):
                    continue  # "the next allowed status is Completed" is not a claim about now
                claimed = next(name for i, name in enumerate(STATUS_WORDS) if m.group(f"s{i}"))
                if claimed != known[wid]:
                    issues.append(f"status claim {wid}={claimed} contradicts {known[wid]}")
        return issues

    @staticmethod
    def _count_claims(text: str, evidence: "Evidence | None") -> tuple[str, list[str]]:
        """Check "N work orders" against roster counts; return the text with those claims removed."""
        issues = []
        proven = evidence.roster_counts() if evidence is not None else set()
        for m in COUNT_CLAIM.finditer(text):
            n = m.group("n").lower()
            n = NUMBER_WORDS.get(n, n)
            if n not in proven:
                issues.append(f"work-order count {n} not in roster counts")
        return COUNT_CLAIM.sub(" ", text), issues

    def _claims_ok(self, text: str, allowed: str, evidence: "Evidence | None" = None) -> list[str]:
        text, issues = self._count_claims(text, evidence)
        for code in set(ASSET_RE.findall(text)):
            if code not in allowed:
                issues.append(f"unknown asset code {code}")
        issues += self._status_claims(text, evidence)
        if ACTION_CLAIM.search(text):
            issues.append("claims an action that was not performed in this turn")
        allowed_nums = _numbers(allowed)
        for n in _numbers(text):
            if n not in allowed_nums:
                issues.append(f"unsupported number {n}")
        for wid in set(ID_RE.findall(text)):
            if wid not in allowed:
                issues.append(f"unknown work order {wid}")
        for d in set(DATE_RE.findall(text)):
            if d not in allowed:
                issues.append(f"unsupported date {d}")
        for st in STATUS_NAMES:
            if st in text and st not in allowed:
                issues.append(f"unsupported status {st}")
        if MARKUP_RE.search(text):
            issues.append("markup in answer")
        return issues

    def _missing(self, spans: list[str], message: str) -> list[str]:
        pool = set(tokens(message))
        keep = []
        for span in spans:
            toks = [t for t in tokens(span) if len(t) > 2]
            if toks and sum(t in pool for t in toks) / len(toks) >= 0.6:
                keep.append(span.strip())
        return keep[:5]

    def verify(self, reply: RespondArgs, evidence: Evidence) -> VerifiedReply:
        issues: list[str] = []
        cited: dict[str, list[str]] = {}
        cited_ids_any: list[str] = []
        for c in reply.citations:
            if self.kb.get(c.section_id) is None:
                issues.append(f"unknown section {c.section_id}")
                continue
            cited_ids_any.append(c.section_id)
            if self.kb.quote_in_section(c.section_id, c.quote):
                cited.setdefault(c.section_id, []).append(c.quote)
            else:
                issues.append(f"quote not found in {c.section_id}")
        missing = self._missing(reply.missing, evidence.user_message)
        section_text = " ".join(
            f"{sec.id} section {sec.number} {sec.heading} {sec.body}"
            for sec in (self.kb.get(s) for s in cited) if sec)
        allowed = " ".join([section_text, evidence.text()])
        allowed_facts = " ".join([section_text, evidence.text(include_user=False)])

        if reply.kind == "unsupported":
            srcs = self._sources(cited) if cited else []
            return VerifiedReply("unsupported", ABSTAIN, srcs, missing)

        if reply.kind == "refuse":
            return VerifiedReply("refuse", self.refusal(evidence, reply.text))

        if reply.kind == "clarify":
            text = reply.text or GENERIC_CLARIFY
            problems = self._claims_ok(text, allowed, evidence)
            if problems:
                return VerifiedReply("clarify", GENERIC_CLARIFY, issues=problems)
            return VerifiedReply("clarify", text, self._sources(cited) if cited else [])

        # kind == "answer"
        text = reply.text
        has_tool_evidence = bool(evidence.tool_data) or bool(COUNT_CLAIM.search(text)) or bool(
            set(ID_RE.findall(text)) & set(ID_RE.findall(evidence.text(include_user=False))))
        if not cited and not has_tool_evidence:
            if cited_ids_any or issues:
                return self._fallback(cited_ids_any, missing, issues)
            if len(text) <= 280 and not _numbers(text) and not DOMAIN_TERMS.search(text) and not MARKUP_RE.search(text):
                return VerifiedReply("smalltalk", text or CAPABILITIES)
            return VerifiedReply("unsupported", ABSTAIN, [], missing, ["answer without evidence"])
        problems = self._claims_ok(text, allowed_facts, evidence)
        if problems or issues or not text:
            return self._fallback(cited_ids_any, missing, issues + problems + ([] if text else ["empty answer"]))
        return VerifiedReply("partial" if missing else "answer", text, self._sources(cited), missing)

    def _refusal_lead_ok(self, lead: str, evidence: Evidence) -> bool:
        """The model's own opening sentence for a refusal: tone only, never a fact."""
        if not lead or len(lead) > MAX_REFUSAL_LEAD_CHARS or not DENIAL_CUE.search(lead):
            return False
        if OWNERSHIP_CLAIM.search(lead) or ID_RE.search(lead) or _numbers(lead) or DATE_RE.search(lead):
            return False
        if ASSET_RE.search(lead) or any(st in lead for st in STATUS_NAMES):
            return False
        if ACTION_CLAIM.search(lead) or MARKUP_RE.search(lead):
            return False
        asked = set(tokens(evidence.user_message))
        if any(t.lower() not in asked for t in DOMAIN_TERMS.findall(lead)):
            return False  # no maintenance terms the technician did not use
        for sentence in re.split(r"(?<=[.!?;:])\s+", lead):  # no names they did not type
            words = re.findall(r"[A-Za-z][\w']*", sentence)
            if words and words[0].lower() not in (STOPWORDS | ALWAYS_CAPITALISED | SENTENCE_STARTERS | asked):
                return False
            for word in words[1:]:
                if word[0].isupper() and word.lower() not in ALWAYS_CAPITALISED and word.lower() not in asked:
                    return False
        return True

    def refusal(self, evidence: Evidence, lead: str = "") -> str:
        owned = {w.get("id") for w in evidence.roster}
        asked = ID_RE.findall(evidence.user_message) + [
            str(d.get("id")) for d in evidence.tool_data if d.get("available") is False and d.get("id")]
        foreign = [wid for wid in dict.fromkeys(asked) if wid not in owned]
        if foreign:  # fixed wording: nothing may hint whether the order is someone else's or missing
            parts = [NOT_AVAILABLE.format(id=foreign[0])]
        else:
            lead = " ".join(lead.split())
            parts = [lead if self._refusal_lead_ok(lead, evidence) else SCOPE_REFUSAL]
        n = len(evidence.roster)
        parts.append(ROSTER_LINE.format(n=n, s="" if n == 1 else "s"))
        return " ".join(parts)

    def _fallback(self, section_ids: list[str], missing: list[str], issues: list[str]) -> VerifiedReply:
        valid = [s for s in dict.fromkeys(section_ids) if self.kb.get(s)]
        if not valid:
            return VerifiedReply("unsupported", ABSTAIN, [], missing, issues)
        return VerifiedReply("fallback", UNVERIFIED, self._sources({s: [] for s in valid}), missing, issues)


def normalize_for_compare(text: str) -> str:  # re-export for tests
    return normalize(text)
