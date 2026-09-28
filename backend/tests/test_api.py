import uuid

from fastapi.testclient import TestClient

from app.config import Settings
from tests.harness import Harness


def test_health_and_meta(tmp_path):
    h = Harness(tmp_path)
    assert h.client.get("/api/health").json()["ok"] is True
    meta = h.client.get("/api/meta").json()
    assert meta["provider"] == "offline" and meta["is_llm"] is False
    assert "key" not in str(meta).lower()


def test_work_orders_endpoint_lists_only_own(tmp_path):
    h = Harness(tmp_path)
    ids = [w["id"] for w in h.client.get("/api/work-orders").json()["work_orders"]]
    assert "WO-004" not in ids and "WO-007" not in ids and len(ids) == 7


def test_session_cookie_scoping(tmp_path):
    h = Harness(tmp_path)
    other = TestClient(h.app)
    assert other.get(f"/api/sessions/{h.sid}").status_code == 404
    other.post("/api/sessions")  # other browser gets its own cookie
    assert other.get(f"/api/sessions/{h.sid}").status_code == 404
    r = other.post(f"/api/sessions/{h.sid}/messages", json={"request_id": str(uuid.uuid4()), "message": "Show WO-003"})
    assert r.status_code == 404
    assert h.client.get(f"/api/sessions/{h.sid}").status_code == 200


def test_history_persisted(tmp_path):
    h = Harness(tmp_path)
    h.say("Show WO-003")
    view = h.client.get(f"/api/sessions/{h.sid}").json()
    assert [m["role"] for m in view["messages"]] == ["user", "assistant"]
    assert view["state"]["active_work_order_id"] == "WO-003"


def test_cross_origin_post_rejected(tmp_path):
    h = Harness(tmp_path)
    r = h.client.post(f"/api/sessions/{h.sid}/messages", headers={"Origin": "https://evil.example"},
                      json={"request_id": str(uuid.uuid4()), "message": "Mark WO-003 complete"})
    assert r.status_code == 403 and h.status("WO-003") == "On Hold"
    ok = h.client.post(f"/api/sessions/{h.sid}/messages", headers={"Origin": "http://localhost:8000"},
                       json={"request_id": str(uuid.uuid4()), "message": "hi"})
    assert ok.status_code == 200


def test_request_validation(tmp_path):
    h = Harness(tmp_path)
    url = f"/api/sessions/{h.sid}/messages"
    assert h.client.post(url, json={"request_id": "nope", "message": "hi"}).status_code == 422
    assert h.client.post(url, json={"request_id": str(uuid.uuid4()), "message": "hi", "role": "admin"}).status_code == 422
    assert h.client.post(url, json={"request_id": str(uuid.uuid4()), "message": "   "}).status_code == 422
    assert h.client.post(url, json={"request_id": str(uuid.uuid4()), "message": "x" * 8001}).status_code == 413


def test_receipt_endpoint(tmp_path):
    h = Harness(tmp_path)
    rid = str(uuid.uuid4())
    body = h.post("Show WO-003", rid=rid).json()
    got = h.client.get(f"/api/sessions/{h.sid}/requests/{rid}")
    assert got.status_code == 200 and got.json() == body
    assert h.client.get(f"/api/sessions/{h.sid}/requests/{uuid.uuid4()}").status_code == 404


def test_busy_session_returns_409(tmp_path):
    h = Harness(tmp_path)
    lock = h.app.state.chat._session_lock(h.sid)
    lock.acquire()
    try:
        r = h.post("hi")
        assert r.status_code == 409
    finally:
        lock.release()
    assert h.post("hi").status_code == 200  # reservation was released


def test_missing_key_fails_startup():
    import pytest
    with pytest.raises(ValueError):
        Settings(model_provider="openai", model_name="some-model", model_api_key="")
    with pytest.raises(ValueError):
        Settings(model_provider="anthropic", model_name="", model_api_key="k")
    Settings(model_provider="openai", model_name="llama3.1", model_base_url="http://localhost:11434/v1")
