"""Pure domain policy: statuses, legal transitions, error codes, result envelopes.

Nothing here touches I/O, HTTP or a model. Every rule that must survive an
adversarial model lives in this module or in ``service.py``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Status(str, Enum):
    OPEN = "Open"
    IN_PROGRESS = "In Progress"
    ON_HOLD = "On Hold"
    COMPLETED = "Completed"


# The only legal edges. Completed is terminal. Same-state is not an edge.
TRANSITIONS: dict[Status, Status] = {
    Status.OPEN: Status.IN_PROGRESS,
    Status.IN_PROGRESS: Status.ON_HOLD,
    Status.ON_HOLD: Status.COMPLETED,
}

STATUS_VALUES: tuple[str, ...] = tuple(s.value for s in Status)
WORK_ORDER_ID_PATTERN = r"^WO-[0-9]{3}$"
WORK_ORDER_ID_RE = re.compile(WORK_ORDER_ID_PATTERN)


def next_status(current: Status) -> Status | None:
    return TRANSITIONS.get(current)


def is_legal_transition(current: Status, target: Status) -> bool:
    return TRANSITIONS.get(current) == target


class ErrorCode(str, Enum):
    OK = "OK"
    UNKNOWN_TOOL = "UNKNOWN_TOOL"
    INVALID_ARGUMENTS = "INVALID_ARGUMENTS"
    ACCESS_DENIED_OR_NOT_FOUND = "ACCESS_DENIED_OR_NOT_FOUND"
    INVALID_TRANSITION = "INVALID_TRANSITION"
    INTENT_MISMATCH = "INTENT_MISMATCH"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    MULTIPLE_ACTIONS = "MULTIPLE_ACTIONS"
    CONFLICT = "CONFLICT"
    LIMIT_REACHED = "LIMIT_REACHED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    code: ErrorCode
    message: str
    data: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "code": self.code.value, "message": self.message, "data": self.data}

    @staticmethod
    def fail(code: ErrorCode, message: str, data: dict[str, Any] | None = None) -> "ToolResult":
        return ToolResult(False, code, message, data)


@dataclass
class WorkOrder:
    id: str
    title: str
    asset_type: str
    assigned_tech: str
    status: Status
    due_date: str
    steps: list[str] = field(default_factory=list)
    version: int = 1
    escalated: bool = False

    def public_view(self) -> dict[str, Any]:
        """Allowlisted fields only; assigned_tech is never echoed to the model/UI."""
        return {
            "id": self.id,
            "title": self.title,
            "assetType": self.asset_type,
            "status": self.status.value,
            "dueDate": self.due_date,
            "steps": list(self.steps),
            "version": self.version,
            "escalated": self.escalated,
            "allowedNextStatus": (n.value if (n := next_status(self.status)) else None),
        }


class SeedError(ValueError):
    """Raised when the work-order fixture is invalid."""


def validate_seed(payload: dict[str, Any]) -> tuple[dict[str, str], list[WorkOrder]]:
    """Validate the immutable fixture and convert it to domain objects."""
    user = payload.get("currentUser")
    if not isinstance(user, dict) or not isinstance(user.get("id"), str) or not user["id"].strip():
        raise SeedError("currentUser.id is required")
    orders_raw = payload.get("workOrders")
    if not isinstance(orders_raw, list) or not orders_raw:
        raise SeedError("workOrders must be a non-empty list")
    seen: set[str] = set()
    orders: list[WorkOrder] = []
    for raw in orders_raw:
        try:
            wid = raw["id"]
            if not WORK_ORDER_ID_RE.match(wid):
                raise SeedError(f"bad id {wid!r}")
            if wid in seen:
                raise SeedError(f"duplicate id {wid}")
            seen.add(wid)
            if raw["status"] not in STATUS_VALUES:
                raise SeedError(f"bad status for {wid}")
            if not str(raw["assignedTech"]).strip():
                raise SeedError(f"missing assignee for {wid}")
            orders.append(
                WorkOrder(
                    id=wid,
                    title=str(raw["title"]),
                    asset_type=str(raw["assetType"]),
                    assigned_tech=str(raw["assignedTech"]),
                    status=Status(raw["status"]),
                    due_date=str(raw["dueDate"]),
                    steps=[str(s) for s in raw.get("steps", [])],
                )
            )
        except KeyError as exc:  # pragma: no cover - defensive
            raise SeedError(f"missing field {exc}") from exc
    return {"id": user["id"], "name": str(user.get("name", user["id"])), "role": str(user.get("role", ""))}, orders
