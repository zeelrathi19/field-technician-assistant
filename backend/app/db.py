"""SQLite persistence: schema, one-time seed, short explicit transactions.

The fixture JSON is immutable seed input. After the first start the database is
the source of truth; restarts never re-seed over user changes.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .domain import SeedError, Status, WorkOrder, validate_seed

SCHEMA_VERSION = "1"

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS work_orders (
  id TEXT PRIMARY KEY, title TEXT NOT NULL, asset_type TEXT NOT NULL,
  assigned_tech TEXT NOT NULL, status TEXT NOT NULL, due_date TEXT NOT NULL,
  steps_json TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
  escalated INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS notes (
  id TEXT PRIMARY KEY, work_order_id TEXT NOT NULL REFERENCES work_orders(id),
  actor_id TEXT NOT NULL, text TEXT NOT NULL, created_at TEXT NOT NULL, request_id TEXT
);
CREATE TABLE IF NOT EXISTS escalations (
  id TEXT PRIMARY KEY, work_order_id TEXT NOT NULL REFERENCES work_orders(id),
  actor_id TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL, request_id TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, browser_id TEXT NOT NULL,
  focus_id TEXT, candidates_json TEXT NOT NULL DEFAULT '[]', pending_json TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
  request_id TEXT, seq INTEGER NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS messages_session_seq ON messages(session_id, seq);
CREATE TABLE IF NOT EXISTS requests (
  user_id TEXT NOT NULL, session_id TEXT NOT NULL, request_id TEXT NOT NULL,
  input_hash TEXT NOT NULL, state TEXT NOT NULL, response_json TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  PRIMARY KEY (user_id, session_id, request_id)
);
CREATE TABLE IF NOT EXISTS audit_events (
  id TEXT PRIMARY KEY, request_id TEXT, actor_id TEXT NOT NULL, tool TEXT NOT NULL,
  work_order_id TEXT, old_status TEXT, new_status TEXT, old_version INTEGER,
  new_version INTEGER, code TEXT NOT NULL, created_at TEXT NOT NULL
);
"""


def utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_id() -> str:
    return str(uuid.uuid4())


class DatabaseError(RuntimeError):
    pass


class Database:
    """Thin wrapper; every connection is short-lived and uses autocommit + explicit BEGIN."""

    def __init__(self, path: Path | str):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5.0, isolation_level=None, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """BEGIN IMMEDIATE: take the write lock *before* reading the state we check."""
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            else:
                conn.execute("COMMIT")
        finally:
            conn.close()

    # ---- lifecycle ------------------------------------------------------------------
    def initialize(self, work_orders_path: Path) -> dict[str, str]:
        """Create schema, seed an empty DB once, refuse a changed seed over existing data."""
        raw_bytes = Path(work_orders_path).read_bytes()
        seed_hash = hashlib.sha256(raw_bytes).hexdigest()
        try:
            payload = json.loads(raw_bytes)
        except json.JSONDecodeError as exc:
            raise SeedError(f"work orders fixture is not valid JSON: {exc}") from exc
        user, orders = validate_seed(payload)

        conn = self._connect()
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(SCHEMA)
        finally:
            conn.close()

        with self.transaction() as tx:
            meta = {r["key"]: r["value"] for r in tx.execute("SELECT key, value FROM schema_meta")}
            if not meta:
                tx.execute("INSERT INTO schema_meta VALUES ('schema_version', ?)", (SCHEMA_VERSION,))
                tx.execute("INSERT INTO schema_meta VALUES ('seed_sha256', ?)", (seed_hash,))
                tx.execute("INSERT INTO users VALUES (?, ?, ?)", (user["id"], user["name"], user["role"]))
                for wo in orders:
                    tx.execute(
                        "INSERT INTO work_orders VALUES (?,?,?,?,?,?,?,?,?)",
                        (wo.id, wo.title, wo.asset_type, wo.assigned_tech, wo.status.value,
                         wo.due_date, json.dumps(wo.steps), 1, 0),
                    )
            else:
                if meta.get("schema_version") != SCHEMA_VERSION:
                    raise DatabaseError("Database schema version is incompatible; run `make reset-db`.")
                if meta.get("seed_sha256") != seed_hash:
                    raise DatabaseError(
                        "The work-order fixture changed after this database was seeded. "
                        "Refusing to merge; run `make reset-db` to reseed deliberately."
                    )
            # Any request left 'processing' by a crash is interrupted, never auto-executed.
            tx.execute(
                "UPDATE requests SET state='interrupted', updated_at=? WHERE state='processing'",
                (utcnow(),),
            )
        return user

    def principal(self) -> dict[str, str]:
        with self.read() as conn:
            row = conn.execute("SELECT id, name, role FROM users LIMIT 1").fetchone()
        if row is None:
            raise DatabaseError("database is not initialized")
        return dict(row)


# ---- row mapping helpers ----------------------------------------------------------------

def row_to_work_order(row: sqlite3.Row) -> WorkOrder:
    return WorkOrder(
        id=row["id"],
        title=row["title"],
        asset_type=row["asset_type"],
        assigned_tech=row["assigned_tech"],
        status=Status(row["status"]),
        due_date=row["due_date"],
        steps=json.loads(row["steps_json"]),
        version=row["version"],
        escalated=bool(row["escalated"]),
    )


def fetch_work_order(conn: sqlite3.Connection, work_order_id: str) -> WorkOrder | None:
    row = conn.execute("SELECT * FROM work_orders WHERE id = ?", (work_order_id,)).fetchone()
    return row_to_work_order(row) if row else None


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
