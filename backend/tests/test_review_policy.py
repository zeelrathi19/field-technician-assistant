"""Regression tests: guardrail and grounding flaws found in review (29 Sep 2026)."""

import pytest

from app.domain import Status
from app.grounding import AnswerVerifier, Evidence
from app.intent import IntentGuard, TurnFacts, extract_ids
from app.llm.scripted import ScriptedModel, call, decide, respond
from app.tools import RespondArgs, ToolDispatcher
from tests.harness import Harness

ROSTER = [{"id": "WO-003", "title": "Compressor lockout", "assetType": "CU-4400", "status": "On Hold",
           "dueDate": "2026-07-16", "allowedNextStatus": "Completed"},
          {"id": "WO-005", "title": "Routine filter", "assetType": "AF-200", "status": "Completed",
           "dueDate": "2026-07-10", "allowedNextStatus": None}]


def R(text, kind="answer", citations=()):
    return RespondArgs(kind=kind, text=text, citations=[dict(section_id=s, quote=q) for s, q in citations], missing=[])


# F1: a status claim about one order was accepted because *another* order had that status.
@pytest.mark.parametrize("text", ["WO-003 is Completed.", "WO-003 is done.", "WO-003 has been completed already.",
                                  "Good news: WO-003 is closed."])
def test_status_claim_must_match_that_order(kb, text):
    v = AnswerVerifier(kb).verify(R(text), Evidence("status of WO-003?", roster=ROSTER))
    assert not v.verified and "WO-003" not in v.text


def test_true_status_claim_passes(kb):
    v = AnswerVerifier(kb).verify(R("WO-003 is On Hold; the next allowed status is Completed."),
                                  Evidence("status of WO-003?", roster=ROSTER))
    assert v.verified, v.issues


# F2: the model could claim an action happened in a turn where nothing was written.
@pytest.mark.parametrize("text", ["I've marked WO-003 as complete.", "Done — I added a note to WO-003.",
                                  "WO-003 has been escalated to your supervisor.", "I updated the status of WO-003."])
def test_action_claims_without_a_write_rejected(kb, text):
    v = AnswerVerifier(kb).verify(R(text), Evidence("mark WO-003 complete", roster=ROSTER))
    assert not v.verified


def test_action_claim_end_to_end_not_shown(tmp_path):
    h = Harness(tmp_path, ScriptedModel([respond("answer", "I've marked WO-003 as complete.")]))
    b = h.say("Mark WO-003 complete")
    assert "marked" not in b["reply"]["text"] and h.status("WO-003") == "On Hold"


# F3: asset identifiers (CU-9999) bypassed the provenance check because digits after '-' were skipped.
def test_unknown_asset_code_rejected(kb):
    v = AnswerVerifier(kb).verify(R("Use the CU-9999 reset sequence.", citations=[("kb-1", "Hold the RESET button for 5 seconds")]),
                                  Evidence("reset?", roster=ROSTER))
    assert not v.verified


def test_known_asset_code_accepted(kb):
    v = AnswerVerifier(kb).verify(R("WO-003 is a CU-4400 unit and is On Hold."), Evidence("asset?", roster=ROSTER))
    assert v.verified, v.issues


# F4: negation anywhere in the message blocked unrelated actions ("never mind the note").
g, d = IntentGuard(), ToolDispatcher()


def facts(msg):
    return TurnFacts(msg, extract_ids(msg), None, False, {"WO-003"})


def test_negation_only_blocks_the_negated_action():
    upd = d.parse("c", "update_status", '{"id":"WO-003","status":"Completed"}')
    assert g.check_intent(upd, facts("Complete WO-003, never mind the note"), Status.ON_HOLD) is None
    assert g.check_intent(upd, facts("Don't complete WO-003"), Status.ON_HOLD) is not None
    assert g.check_intent(upd, facts("Do not mark WO-003 as done"), Status.ON_HOLD) is not None


def test_polite_request_is_not_a_hypothetical():
    upd = d.parse("c", "update_status", '{"id":"WO-003","status":"Completed"}')
    assert g.check_intent(upd, facts("Can you mark WO-003 complete please?"), Status.ON_HOLD) is None
    assert g.check_intent(upd, facts("Could you close WO-003?"), Status.ON_HOLD) is None
    assert g.check_intent(upd, facts("How do I close WO-003?"), Status.ON_HOLD) is not None
