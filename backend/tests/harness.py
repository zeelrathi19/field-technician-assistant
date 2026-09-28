from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.config import Settings
from app.db import Database
from app.main import create_app
from tests.conftest import count, status_of  # noqa: F401  (re-export)


class Harness:
    def __init__(self, tmp_path: Path, model: Any = None, **overrides: Any):
        self.tmp_path = tmp_path
        self.settings = Settings(model_provider="offline", database_path=tmp_path / "app.sqlite3",
                                 frontend_dist=tmp_path / "no-ui", **overrides)
        self.app = create_app(self.settings, model=model)
        self.client = TestClient(self.app)
        self.db: Database = self.app.state.chat.db
        self.sid = self.new_session()

    def new_session(self, client: TestClient | None = None) -> str:
        return (client or self.client).post("/api/sessions").json()["session_id"]

    def post(self, text: str, sid: str | None = None, rid: str | None = None, client: TestClient | None = None):
        return (client or self.client).post(f"/api/sessions/{sid or self.sid}/messages",
                                           json={"request_id": rid or str(uuid.uuid4()), "message": text})

    def say(self, text: str, **kw: Any) -> dict[str, Any]:
        r = self.post(text, **kw)
        assert r.status_code == 200, (r.status_code, r.text)
        body = r.json()
        body["reply"] = body["messages"][-1]
        return body

    def status(self, wid: str) -> str:
        return status_of(self.db, wid)

    def count(self, table: str, where: str = "1=1", params: tuple = ()) -> int:
        return count(self.db, table, where, params)

    def writes(self) -> int:
        return self.count("audit_events", "code='OK'")
