import itertools

import pytest

from app.domain import SeedError, Status, is_legal_transition, next_status, validate_seed

LEGAL = {(Status.OPEN, Status.IN_PROGRESS), (Status.IN_PROGRESS, Status.ON_HOLD), (Status.ON_HOLD, Status.COMPLETED)}


@pytest.mark.parametrize("cur,tgt", list(itertools.product(Status, Status)))
def test_all_sixteen_status_pairs(cur, tgt):
    assert is_legal_transition(cur, tgt) == ((cur, tgt) in LEGAL)


def test_completed_is_terminal():
    assert next_status(Status.COMPLETED) is None


@pytest.mark.parametrize("payload", [
    {},
    {"currentUser": {"id": ""}, "workOrders": [{}]},
    {"currentUser": {"id": "u"}, "workOrders": []},
    {"currentUser": {"id": "u"}, "workOrders": [
        {"id": "WO-001", "title": "t", "assetType": "a", "assignedTech": "u", "status": "Closed", "dueDate": "d"}]},
    {"currentUser": {"id": "u"}, "workOrders": [
        {"id": "WO-001", "title": "t", "assetType": "a", "assignedTech": "u", "status": "Open", "dueDate": "d"},
        {"id": "WO-001", "title": "t", "assetType": "a", "assignedTech": "u", "status": "Open", "dueDate": "d"}]},
])
def test_invalid_seed_rejected(payload):
    with pytest.raises(SeedError):
        validate_seed(payload)
