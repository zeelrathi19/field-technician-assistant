"""Regression tests: orchestration, persistence and HTTP reliability flaws found in review."""

import threading
import uuid

from app.llm.scripted import ScriptedModel, respond
from tests.harness import Harness


def test_oversized_body_rejected_before_parsing(tmp_path):
    h = Harness(tmp_path)
    r = h.client.post(f"/api/sessions/{h.sid}/messages", content=b'{"request_id":"x","message":"' + b"a" * 200_000 + b'"}',
                      headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_unknown_api_path_is_404_json_not_the_spa(tmp_path):
    dist = tmp_path / "ui"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>")
    h = Harness(tmp_path, frontend_dist=dist)
    assert h.client.get("/").text == "<html>app</html>"
    assert h.client.get("/some/client/route").text == "<html>app</html>"
    r = h.client.get("/api/does-not-exist")
    assert r.status_code == 404 and r.headers["content-type"].startswith("application/json")


def test_session_locks_do_not_leak(tmp_path):
    h = Harness(tmp_path)
    for _ in range(3):
        h.say("hi")
    sid2 = h.new_session()
    h.say("hi", sid=sid2)
    assert h.app.state.chat._locks == {}


def test_concurrent_distinct_messages_in_one_session_one_wins(tmp_path):
    gate = threading.Event()
    release = threading.Event()

    def slow(_msgs):
        gate.set()
        release.wait(5)
        return respond("answer", "Hello!")

    h = Harness(tmp_path, ScriptedModel([slow]))
    results = {}

    def first():
        results["a"] = h.post("hi")

    t = threading.Thread(target=first)
    t.start()
    gate.wait(5)
    results["b"] = h.post("hello again")
    release.set()
    t.join(5)
    assert results["a"].status_code == 200 and results["b"].status_code == 409
    assert h.app.state.chat._locks == {}


def test_receipt_is_scoped_to_its_session(tmp_path):
    h = Harness(tmp_path)
    rid = str(uuid.uuid4())
    h.post("hi", rid=rid)
    other = h.new_session()
    assert h.client.get(f"/api/sessions/{other}/requests/{rid}").status_code == 404


def test_health_reports_provider_without_secrets(tmp_path):
    h = Harness(tmp_path)
    body = h.client.get("/api/health").json()
    assert body["provider"] == "offline" and "model_configured" not in body
