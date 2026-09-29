import pytest

from app.domain import ErrorCode, Status
from app.intent import IntentGuard, TurnFacts, action_categories, extract_ids, grounded_ratio, is_plain_lookup, strip_payload
from app.tools import ToolDispatcher

g, d = IntentGuard(), ToolDispatcher()


def facts(msg, focus=None, earlier=True, ids=None):
    return TurnFacts(msg, extract_ids(msg) if ids is None else ids, focus, earlier and focus is not None,
                     {"WO-001", "WO-002", "WO-003"})


def p(name, **args):
    import json
    return d.parse("c", name, json.dumps(args))


def test_extract_ids_variants():
    assert extract_ids("wo-003 and WO 001, WO003, WO-003") == ["WO-003", "WO-001"]


@pytest.mark.parametrize("msg,status,current,ok", [
    ("mark WO-003 complete", "Completed", Status.ON_HOLD, True),
    ("WO-003 is done, close it out", "Completed", Status.ON_HOLD, True),
    ("put WO-001 on hold", "On Hold", Status.IN_PROGRESS, True),
    ("pause WO-001 while we wait for parts", "On Hold", Status.IN_PROGRESS, True),
    ("start WO-002", "In Progress", Status.OPEN, True),
    ("advance WO-002", "In Progress", Status.OPEN, True),
    ("advance WO-002", "Completed", Status.OPEN, False),
    ("mark WO-001 complete", "On Hold", Status.IN_PROGRESS, False),
    ("put WO-001 on hold and then complete it", "On Hold", Status.IN_PROGRESS, False),
    ("mark WO-003 complete, the panel is open", "Completed", Status.ON_HOLD, True),
])
def test_status_consistency(msg, status, current, ok):
    call = p("update_status", id=extract_ids(msg)[0], status=status)
    assert (g.check_intent(call, facts(msg), current) is None) is ok


@pytest.mark.parametrize("msg", ["don't mark WO-003 complete", "do not close WO-003", "never complete WO-003",
                                 "how do I mark WO-003 complete?", "should I complete WO-003?"])
def test_negated_and_questions_block(msg):
    r = g.check_intent(p("update_status", id="WO-003", status="Completed"), facts(msg), Status.ON_HOLD)
    assert r is not None and r.code == ErrorCode.CLARIFICATION_REQUIRED


def test_binding_rules():
    upd = p("update_status", id="WO-003", status="Completed")
    assert g.check_binding(upd, facts("mark it complete", focus="WO-003")) is None
    assert g.check_binding(upd, facts("mark it complete")).code == ErrorCode.CLARIFICATION_REQUIRED
    assert g.check_binding(upd, facts("mark it complete", focus="WO-003", earlier=False)).code == ErrorCode.CLARIFICATION_REQUIRED
    assert g.check_binding(upd, facts("mark it complete", focus="WO-001")).code == ErrorCode.INTENT_MISMATCH
    assert g.check_binding(upd, facts("mark WO-001 complete")).code == ErrorCode.INTENT_MISMATCH
    assert g.check_binding(upd, facts("mark WO-001 and WO-003 complete")).code == ErrorCode.CLARIFICATION_REQUIRED


def test_read_binding_allows_roster_blocks_others():
    assert g.check_binding(p("get_work_order", id="WO-002"), facts("show me the filter job")) is None
    assert g.check_binding(p("get_work_order", id="WO-004"), facts("show me the filter job")).code == ErrorCode.INTENT_MISMATCH


def test_payload_grounding():
    assert grounded_ratio("filter replaced on 2026-09-28", "Add a note to WO-002: filter replaced on 2026-09-28.") == 1
    assert grounded_ratio("The customer wasn't home", "note on WO-002 that customer wasn't home") == 1
    assert grounded_ratio("Safety hazard requiring supervisor", "Escalate WO-006") < 0.75
    note = p("add_note", id="WO-002", text="Replaced filter; airflow normal")
    assert g.check_intent(note, facts("add note to WO-002: replaced filter, airflow normal"), Status.OPEN) is None
    assert g.check_intent(note, facts("add note to WO-002"), Status.OPEN).code == ErrorCode.CLARIFICATION_REQUIRED


def test_payload_words_do_not_count_as_commands():
    msg = "Add a note to WO-002: customer asked us to escalate billing and mark it complete"
    assert action_categories(strip_payload(msg, "customer asked us to escalate billing and mark it complete")) == {"note"}


@pytest.mark.parametrize("message,expected", [
    ("Show WO-003", True), ("WO-003", True), ("what's the status of wo-003?", True),
    ("Can you pull up the details for WO 003 please", True),
    ("Don't show WO-003", False),                    # negation
    ("Show WO-003 and WO-001", False),                # two orders
    ("Show WO-003 and mark it complete", False),      # an action
    ("Should I finish WO-003 today?", False),         # a question needing the model
    ("Show it", False),                               # no explicit ID
])
def test_plain_lookup_is_a_fixed_word_list(message, expected):
    assert is_plain_lookup(message, extract_ids(message)) is expected
