from __future__ import annotations

from pathlib import Path

import pytest

from app.db import Database
from app.knowledge import KnowledgeBase
from app.service import WorkOrderService

ROOT = Path(__file__).resolve().parents[2]
WORK_ORDERS = ROOT / "inputs" / "work_orders.json"
KNOWLEDGE = ROOT / "inputs" / "knowledge.md"


@pytest.fixture
def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "t.sqlite3")
    database.initialize(WORK_ORDERS)
    return database


@pytest.fixture
def service() -> WorkOrderService:
    return WorkOrderService("tech-ravi")


@pytest.fixture(scope="session")
def kb() -> KnowledgeBase:
    return KnowledgeBase.load(KNOWLEDGE)


def status_of(db: Database, wid: str) -> str:
    with db.read() as c:
        return c.execute("SELECT status FROM work_orders WHERE id=?", (wid,)).fetchone()[0]


def count(db: Database, table: str, where: str = "1=1", params: tuple = ()) -> int:
    with db.read() as c:
        return c.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", params).fetchone()[0]
