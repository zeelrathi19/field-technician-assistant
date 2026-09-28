import json
import threading

import pytest

from app.db import Database, DatabaseError
from app.domain import ErrorCode, Status
from tests.conftest import WORK_ORDERS, count, status_of

FOREIGN = ["WO-004", "WO-007", "WO-009", "WO-999"]


@pytest.mark.parametrize("wid", FOREIGN)
def test_get_denies_foreign_and_missing_identically(db, service, wid):
    with db.read() as c:
        r = service.get(c, wid)
    assert not r.ok and r.code == ErrorCode.ACCESS_DENIED_OR_NOT_FOUND
    assert "priya" not in r.message.lower() and "arjun" not in r.message.lower()
    assert r.data == {"id": wid}


@pytest.mark.parametrize("wid", FOREIGN)
@pytest.mark.parametrize("op", ["status", "note", "escalate"])
def test_mutations_denied_on_foreign(db, service, wid, op):
    before = status_of(db, wid) if wid != "WO-999" else None
    with db.transaction() as c:
        if op == "status":
            r = service.update_status(c, wid, "On Hold")
        elif op == "note":
            r = service.add_note(c, wid, "Inspected")
        else:
            r = service.escalate(c, wid, "Water hazard")
    assert r.code == ErrorCode.ACCESS_DENIED_OR_NOT_FOUND
    assert count(db, "notes") == 0 and count(db, "escalations") == 0
    if before:
        assert status_of(db, wid) == before


@pytest.mark.parametrize("wid,cur,nxt", [("WO-002", "Open", "In Progress"), ("WO-001", "In Progress", "On Hold"),
                                          ("WO-003", "On Hold", "Completed")])
def test_legal_transition_persists_once(db, service, wid, cur, nxt):
    with db.transaction() as c:
        r = service.update_status(c, wid, nxt, request_id="r1")
    assert r.ok and r.data["previousStatus"] == cur and r.data["status"] == nxt
    assert status_of(db, wid) == nxt
    assert count(db, "audit_events", "code='OK' AND work_order_id=?", (wid,)) == 1


@pytest.mark.parametrize("wid,target", [("WO-002", "Completed"), ("WO-001", "Completed"), ("WO-001", "In Progress"),
                                         ("WO-005", "Open"), ("WO-003", "On Hold"), ("WO-002", "On Hold")])
def test_illegal_transitions_refused_without_change(db, service, wid, target):
    before = status_of(db, wid)
    with db.transaction() as c:
        r = service.update_status(c, wid, target)
    assert r.code == ErrorCode.INVALID_TRANSITION
    assert status_of(db, wid) == before


def test_invalid_transition_message_names_allowed_next(db, service):
    with db.transaction() as c:
        r = service.update_status(c, "WO-001", "Completed")
    assert "On Hold" in r.message and r.data["allowedNextStatus"] == "On Hold"


def test_notes_and_escalations_allowed_on_completed(db, service):
    with db.transaction() as c:
        assert service.add_note(c, "WO-005", "Customer confirmed airflow").ok
        assert service.escalate(c, "WO-005", "Customer disputes warranty").ok
    assert status_of(db, "WO-005") == "Completed"


def test_escalation_sets_flag_keeps_status(db, service):
    with db.transaction() as c:
        r = service.escalate(c, "WO-006", "exposed wiring was found")
    assert r.ok and "no email" in r.message
    assert status_of(db, "WO-006") == "In Progress"
    with db.read() as c:
        assert c.execute("SELECT escalated FROM work_orders WHERE id='WO-006'").fetchone()[0] == 1


def test_version_conflict(db, service):
    with db.transaction() as c:
        r = service.update_status(c, "WO-002", "In Progress", expected_version=99)
    assert r.code == ErrorCode.CONFLICT and status_of(db, "WO-002") == "Open"


def test_rollback_on_failure(db, service):
    with pytest.raises(RuntimeError):
        with db.transaction() as c:
            assert service.update_status(c, "WO-002", "In Progress").ok
            raise RuntimeError("boom")
    assert status_of(db, "WO-002") == "Open"
    assert count(db, "audit_events") == 0


def test_concurrent_same_transition_only_one_wins(db, service):
    results = []
    barrier = threading.Barrier(2)

    def worker():
        barrier.wait()
        with db.transaction() as c:
            results.append(service.update_status(c, "WO-002", "In Progress"))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(r.ok for r in results) == [False, True]
    assert status_of(db, "WO-002") == "In Progress"


def test_get_read_bounds_notes(db, service):
    with db.transaction() as c:
        for i in range(7):
            service.add_note(c, "WO-002", f"note {i}")
    with db.read() as c:
        r = service.get(c, "WO-002")
    assert len(r.data["notes"]) == 5 and r.data["notesTruncated"] is True
    assert "assigned_tech" not in r.data and "assignedTech" not in r.data


def test_restart_keeps_changes_and_does_not_reseed(db, service, tmp_path):
    with db.transaction() as c:
        service.update_status(c, "WO-002", "In Progress")
    again = Database(db.path)
    again.initialize(WORK_ORDERS)
    assert status_of(again, "WO-002") == "In Progress"


def test_changed_seed_refused(db, tmp_path):
    changed = tmp_path / "wo.json"
    data = json.loads(WORK_ORDERS.read_text())
    data["workOrders"][0]["title"] = "changed"
    changed.write_text(json.dumps(data))
    with pytest.raises(DatabaseError):
        Database(db.path).initialize(changed)


def test_list_own_only(db, service):
    with db.read() as c:
        ids = [w["id"] for w in service.list_own(c)]
    assert ids == ["WO-001", "WO-002", "WO-003", "WO-005", "WO-006", "WO-008", "WO-010"]


def test_status_enum_roundtrip():
    assert [s.value for s in Status] == ["Open", "In Progress", "On Hold", "Completed"]
