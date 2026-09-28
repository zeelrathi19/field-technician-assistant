"""WorkOrderService: the only code allowed to read or change work orders.

Ownership is re-checked against fresh rows on *every* call, including reads.
Mutations must be called inside ``Database.transaction()`` (BEGIN IMMEDIATE), so
the check and the write cannot interleave with another writer.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from .db import dumps, fetch_work_order, new_id, row_to_work_order, utcnow
from .domain import ErrorCode, Status, ToolResult, WorkOrder, next_status

log = logging.getLogger("fta.service")

NOTE_READ_LIMIT = 5
ESCALATION_READ_LIMIT = 3


def unavailable(work_order_id: str) -> ToolResult:
    # Same public message for "not found" and "someone else's": no disclosure.
    return ToolResult.fail(
        ErrorCode.ACCESS_DENIED_OR_NOT_FOUND,
        f"Work order {work_order_id} is not available to you. You can only view or act on work orders assigned to you.",
        {"id": work_order_id},
    )


def transition_refusal(wo: WorkOrder, target: Status) -> ToolResult:
    allowed = next_status(wo.status)
    if wo.status == target:
        msg = f"{wo.id} is already {wo.status.value}. Nothing was changed."
    elif allowed is None:
        msg = f"{wo.id} is Completed. Completed work orders cannot change status. Nothing was changed."
    else:
        msg = (
            f"{wo.id} is {wo.status.value}, so it can't move to {target.value}. "
            f"Status moves one step at a time (Open → In Progress → On Hold → Completed); "
            f"the only allowed next status is {allowed.value}. Nothing was changed."
        )
    return ToolResult.fail(
        ErrorCode.INVALID_TRANSITION,
        msg,
        {"id": wo.id, "status": wo.status.value, "requested": target.value,
         "allowedNextStatus": allowed.value if allowed else None, "version": wo.version},
    )


class WorkOrderService:
    def __init__(self, principal_id: str):
        self.principal_id = principal_id

    # ---- helpers ----------------------------------------------------------------------
    def _owned(self, conn: sqlite3.Connection, work_order_id: str) -> WorkOrder | None:
        wo = fetch_work_order(conn, work_order_id)
        if wo is None or wo.assigned_tech != self.principal_id:
            if wo is not None:
                log.info("ownership_denied", extra={"work_order_id": work_order_id})
            return None
        return wo

    def _audit(self, conn: sqlite3.Connection, *, tool: str, wo_id: str, code: ErrorCode,
               request_id: str | None, old: WorkOrder | None = None, new_status: str | None = None,
               new_version: int | None = None) -> str:
        op_id = new_id()
        conn.execute(
            "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (op_id, request_id, self.principal_id, tool, wo_id,
             old.status.value if old else None, new_status,
             old.version if old else None, new_version, code.value, utcnow()),
        )
        return op_id

    # ---- reads ------------------------------------------------------------------------
    def owns(self, conn: sqlite3.Connection, work_order_id: str) -> bool:
        return self._owned(conn, work_order_id) is not None

    def list_own(self, conn: sqlite3.Connection) -> list[dict[str, Any]]:
        rows = conn.execute(
            "SELECT * FROM work_orders WHERE assigned_tech = ? ORDER BY id", (self.principal_id,)
        ).fetchall()
        out = []
        for r in rows:
            wo = row_to_work_order(r)
            notes = conn.execute("SELECT COUNT(*) FROM notes WHERE work_order_id=?", (wo.id,)).fetchone()[0]
            out.append({
                "id": wo.id, "title": wo.title, "assetType": wo.asset_type, "status": wo.status.value,
                "dueDate": wo.due_date, "version": wo.version, "escalated": wo.escalated,
                "noteCount": notes,
                "allowedNextStatus": (n.value if (n := next_status(wo.status)) else None),
            })
        return out

    def get(self, conn: sqlite3.Connection, work_order_id: str) -> ToolResult:
        wo = self._owned(conn, work_order_id)
        if wo is None:
            return unavailable(work_order_id)
        data = wo.public_view()
        notes = conn.execute(
            "SELECT id, text, created_at FROM notes WHERE work_order_id=? ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (wo.id, NOTE_READ_LIMIT + 1),
        ).fetchall()
        escs = conn.execute(
            "SELECT id, reason, created_at FROM escalations WHERE work_order_id=? ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (wo.id, ESCALATION_READ_LIMIT + 1),
        ).fetchall()
        data["notes"] = [{"id": n["id"], "text": n["text"], "createdAt": n["created_at"]} for n in notes[:NOTE_READ_LIMIT]]
        data["notesTruncated"] = len(notes) > NOTE_READ_LIMIT
        data["escalations"] = [{"id": e["id"], "reason": e["reason"], "createdAt": e["created_at"]} for e in escs[:ESCALATION_READ_LIMIT]]
        return ToolResult(True, ErrorCode.OK, f"Loaded {wo.id}.", data)

    # ---- mutations (call inside Database.transaction) ------------------------------------
    def update_status(self, conn: sqlite3.Connection, work_order_id: str, status: str,
                      request_id: str | None = None, expected_version: int | None = None) -> ToolResult:
        target = Status(status)  # validated upstream; ValueError here is a programming error
        wo = self._owned(conn, work_order_id)
        if wo is None:
            self._audit(conn, tool="update_status", wo_id=work_order_id,
                        code=ErrorCode.ACCESS_DENIED_OR_NOT_FOUND, request_id=request_id)
            return unavailable(work_order_id)
        if expected_version is not None and expected_version != wo.version:
            self._audit(conn, tool="update_status", wo_id=wo.id, code=ErrorCode.CONFLICT,
                        request_id=request_id, old=wo)
            return ToolResult.fail(ErrorCode.CONFLICT,
                                   f"{wo.id} changed since it was read (now {wo.status.value}). Nothing was changed.",
                                   {"id": wo.id, "status": wo.status.value, "version": wo.version})
        if next_status(wo.status) != target:
            self._audit(conn, tool="update_status", wo_id=wo.id, code=ErrorCode.INVALID_TRANSITION,
                        request_id=request_id, old=wo, new_status=target.value)
            return transition_refusal(wo, target)
        cur = conn.execute(
            "UPDATE work_orders SET status=?, version=version+1 WHERE id=? AND version=? AND assigned_tech=?",
            (target.value, wo.id, wo.version, self.principal_id),
        )
        if cur.rowcount != 1:  # defensive: impossible under BEGIN IMMEDIATE
            return ToolResult.fail(ErrorCode.CONFLICT, f"{wo.id} changed concurrently. Nothing was changed.")
        op = self._audit(conn, tool="update_status", wo_id=wo.id, code=ErrorCode.OK, request_id=request_id,
                         old=wo, new_status=target.value, new_version=wo.version + 1)
        return ToolResult(True, ErrorCode.OK,
                          f"{wo.id} status changed from {wo.status.value} to {target.value}.",
                          {"id": wo.id, "previousStatus": wo.status.value, "status": target.value,
                           "version": wo.version + 1, "operationId": op, "at": utcnow()})

    def add_note(self, conn: sqlite3.Connection, work_order_id: str, text: str,
                 request_id: str | None = None) -> ToolResult:
        wo = self._owned(conn, work_order_id)
        if wo is None:
            self._audit(conn, tool="add_note", wo_id=work_order_id,
                        code=ErrorCode.ACCESS_DENIED_OR_NOT_FOUND, request_id=request_id)
            return unavailable(work_order_id)
        note_id, at = new_id(), utcnow()
        conn.execute("INSERT INTO notes VALUES (?,?,?,?,?,?)",
                     (note_id, wo.id, self.principal_id, text, at, request_id))
        conn.execute("UPDATE work_orders SET version=version+1 WHERE id=?", (wo.id,))
        op = self._audit(conn, tool="add_note", wo_id=wo.id, code=ErrorCode.OK, request_id=request_id,
                         old=wo, new_version=wo.version + 1)
        return ToolResult(True, ErrorCode.OK, f"Note added to {wo.id}.",
                          {"id": wo.id, "noteId": note_id, "text": text, "at": at,
                           "version": wo.version + 1, "operationId": op, "status": wo.status.value})

    def escalate(self, conn: sqlite3.Connection, work_order_id: str, reason: str,
                 request_id: str | None = None) -> ToolResult:
        wo = self._owned(conn, work_order_id)
        if wo is None:
            self._audit(conn, tool="escalate", wo_id=work_order_id,
                        code=ErrorCode.ACCESS_DENIED_OR_NOT_FOUND, request_id=request_id)
            return unavailable(work_order_id)
        esc_id, at = new_id(), utcnow()
        conn.execute("INSERT INTO escalations VALUES (?,?,?,?,?,?)",
                     (esc_id, wo.id, self.principal_id, reason, at, request_id))
        conn.execute("UPDATE work_orders SET escalated=1, version=version+1 WHERE id=?", (wo.id,))
        op = self._audit(conn, tool="escalate", wo_id=wo.id, code=ErrorCode.OK, request_id=request_id,
                         old=wo, new_version=wo.version + 1)
        return ToolResult(True, ErrorCode.OK,
                          f"{wo.id} is flagged for supervisor review. The escalation was recorded here; "
                          f"no email or notification was sent. Status is unchanged ({wo.status.value}).",
                          {"id": wo.id, "escalationId": esc_id, "reason": reason, "at": at,
                           "version": wo.version + 1, "operationId": op, "status": wo.status.value})


def dump_result(result: ToolResult) -> str:
    return dumps(result.to_dict())
