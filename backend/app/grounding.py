"""AnswerVerifier: nothing reaches the technician as fact unless code can trace it.

The model may *phrase* an answer, but:
  * every citation must be a verbatim quote from the cited approved section;
  * every number (digits or number words), date, work-order ID and status name in
    the answer must appear in the evidence (cited sections, this turn's tool
    results, the technician's own roster, or the technician's own message);
  * an answer with maintenance content but no evidence is replaced by a fixed
    abstention.
Any failure falls back to deterministic rendering (whole approved sections, or the
fixed abstention). The verifier proves provenance, not relevance.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from .intent import tokens
from .knowledge import KnowledgeBase, normalize
from .tools import RespondArgs

ABSTAIN = "The knowledge base doesn't cover that, so I can't give you an answer or procedure for it. I won't guess."
UNVERIFIED = ("I couldn't verify a summary against the approved sources, so here is the exact knowledge-base text instead.")
GENERIC_CLARIFY = "Could you tell me which work order (for example WO-003) and what you'd like me to do?"
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


@dataclass
class Evidence:
    user_message: str
    tool_data: list[dict[str, Any]] = field(default_factory=list)
    roster: list[dict[str, Any]] = field(default_factory=list)
    focus_id: str | None = None

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

    def _claims_ok(self, text: str, allowed: str) -> list[str]:
        issues = []
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

        if reply.kind in ("clarify", "refuse"):
            text = reply.text or GENERIC_CLARIFY
            problems = self._claims_ok(text, allowed)
            if problems:
                return VerifiedReply(reply.kind, GENERIC_CLARIFY if reply.kind == "clarify" else CAPABILITIES,
                                     issues=problems)
            return VerifiedReply(reply.kind, text, self._sources(cited) if cited else [])

        # kind == "answer"
        text = reply.text
        has_tool_evidence = bool(evidence.tool_data) or bool(
            set(ID_RE.findall(text)) & set(ID_RE.findall(evidence.text(include_user=False))))
        if not cited and not has_tool_evidence:
            if cited_ids_any or issues:
                return self._fallback(cited_ids_any, missing, issues)
            if len(text) <= 280 and not _numbers(text) and not DOMAIN_TERMS.search(text) and not MARKUP_RE.search(text):
                return VerifiedReply("smalltalk", text or CAPABILITIES)
            return VerifiedReply("unsupported", ABSTAIN, [], missing, ["answer without evidence"])
        problems = self._claims_ok(text, allowed_facts)
        if problems or issues or not text:
            return self._fallback(cited_ids_any, missing, issues + problems + ([] if text else ["empty answer"]))
        return VerifiedReply("partial" if missing else "answer", text, self._sources(cited), missing)

    def _fallback(self, section_ids: list[str], missing: list[str], issues: list[str]) -> VerifiedReply:
        valid = [s for s in dict.fromkeys(section_ids) if self.kb.get(s)]
        if not valid:
            return VerifiedReply("unsupported", ABSTAIN, [], missing, issues)
        return VerifiedReply("fallback", UNVERIFIED, self._sources({s: [] for s in valid}), missing, issues)


def normalize_for_compare(text: str) -> str:  # re-export for tests
    return normalize(text)
