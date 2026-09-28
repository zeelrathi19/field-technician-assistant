from app.grounding import ABSTAIN, AnswerVerifier, Evidence
from app.tools import RespondArgs


def R(kind="answer", text="", citations=(), missing=()):
    return RespondArgs(kind=kind, text=text, citations=[dict(section_id=s, quote=q) for s, q in citations], missing=list(missing))


def test_valid_answer_with_companion_lockout(kb):
    v = AnswerVerifier(kb).verify(R(text="Hold RESET for 5 seconds.", citations=[("kb-1", "Hold the RESET button for 5 seconds")]),
                                  Evidence("how to reset"))
    assert v.verified and [s["section_id"] for s in v.sources] == ["kb-1", "kb-2"]


def test_unsupported_ignores_model_text(kb):
    v = AnswerVerifier(kb).verify(R(kind="unsupported", text="Try 40 Nm", missing=["torque for bolts"]),
                                  Evidence("what torque for bolts"))
    assert v.text == ABSTAIN and v.missing == ["torque for bolts"]


def test_missing_spans_must_come_from_question(kb):
    v = AnswerVerifier(kb).verify(R(kind="unsupported", missing=["gas leak repair"]), Evidence("what torque for bolts"))
    assert v.missing == []


def test_unknown_work_order_id_rejected(kb):
    v = AnswerVerifier(kb).verify(R(text="WO-004 is In Progress."), Evidence("status?", tool_data=[{"id": "WO-001"}]))
    assert not v.verified


def test_status_claim_must_match_evidence(kb):
    v = AnswerVerifier(kb).verify(R(text="WO-001 is Completed."), Evidence("status?", tool_data=[{"id": "WO-001", "status": "In Progress"}]))
    assert not v.verified


def test_markup_rejected(kb):
    v = AnswerVerifier(kb).verify(R(text="<img src=x onerror=alert(1)> Labor 90 days",
                                    citations=[("kb-3", "Labor is covered for 90 days")]), Evidence("labor?"))
    assert not v.verified and "<img" not in v.text


def test_clarify_with_invented_id_replaced(kb):
    v = AnswerVerifier(kb).verify(R(kind="clarify", text="Did you mean WO-777?"), Evidence("mark it complete"))
    assert "WO-777" not in v.text
