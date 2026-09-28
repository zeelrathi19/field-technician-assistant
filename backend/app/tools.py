"""Static tool registry, strict argument models, and model-facing JSON schemas.

The model-visible schema and the server validator come from the *same* Pydantic
models, so they cannot drift. Tools are a fixed mapping — no dynamic dispatch.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from .config import MAX_CITATIONS, MAX_RAW_TOOL_ARGS_BYTES, MAX_RESPOND_TEXT_CHARS
from .domain import STATUS_VALUES, WORK_ORDER_ID_PATTERN, ErrorCode, ToolResult

WorkOrderId = Annotated[str, StringConstraints(strip_whitespace=True, pattern=WORK_ORDER_ID_PATTERN)]
StatusValue = Literal["Open", "In Progress", "On Hold", "Completed"]
assert tuple(StatusValue.__args__) == STATUS_VALUES  # type: ignore[attr-defined]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class GetWorkOrderArgs(_Strict):
    id: WorkOrderId


class UpdateStatusArgs(_Strict):
    id: WorkOrderId
    status: StatusValue


class AddNoteArgs(_Strict):
    id: WorkOrderId
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class EscalateArgs(_Strict):
    id: WorkOrderId
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Citation(_Strict):
    section_id: Annotated[str, StringConstraints(pattern=r"^kb-[0-9]{1,2}$")]
    quote: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)]


class RespondArgs(_Strict):
    kind: Literal["answer", "clarify", "unsupported", "refuse"]
    text: Annotated[str, StringConstraints(strip_whitespace=True, max_length=MAX_RESPOND_TEXT_CHARS)]
    citations: list[Citation] = Field(max_length=MAX_CITATIONS)
    missing: list[Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]] = Field(max_length=5)


MUTATING_TOOLS = frozenset({"update_status", "add_note", "escalate"})
BUSINESS_TOOLS = ("get_work_order", "update_status", "add_note", "escalate")
RESPOND_TOOL = "respond"

ARG_MODELS: dict[str, type[_Strict]] = {
    "get_work_order": GetWorkOrderArgs,
    "update_status": UpdateStatusArgs,
    "add_note": AddNoteArgs,
    "escalate": EscalateArgs,
    RESPOND_TOOL: RespondArgs,
}

DESCRIPTIONS = {
    "get_work_order": "Read one of the current technician's work orders (status, due date, recorded steps, notes, escalations).",
    "update_status": (
        "Change a work order's status. Only when the technician explicitly asks in this message. "
        "Legal moves are one step: Open->In Progress->On Hold->Completed. Never chain steps."
    ),
    "add_note": "Append a note to a work order. Only when explicitly asked; text must be the technician's own words.",
    "escalate": (
        "Flag a work order for supervisor review with the technician's stated reason. "
        "Only when explicitly asked. Does not change status or send notifications."
    ),
    RESPOND_TOOL: (
        "Finish the turn with the reply to show the technician. kind=answer (grounded answer), clarify "
        "(ask one question), unsupported (knowledge base does not cover it), refuse (policy). "
        "For maintenance facts cite knowledge-base sections with exact verbatim quotes; list uncovered parts in missing."
    ),
}


@dataclass(frozen=True)
class ParsedCall:
    call_id: str
    name: str
    args: BaseModel

    @property
    def is_mutation(self) -> bool:
        return self.name in MUTATING_TOOLS

    @property
    def target_id(self) -> str | None:
        return getattr(self.args, "id", None)


class _DuplicateKey(ValueError):
    pass


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise _DuplicateKey(key)
        out[key] = value
    return out


def _reject_constant(token: str) -> Any:
    raise ValueError(f"non-finite number {token}")


def strict_json_loads(raw: str) -> Any:
    return json.loads(raw, object_pairs_hook=_no_duplicates, parse_constant=_reject_constant)


class ToolDispatcher:
    """Validates a proposed call. Execution happens in ChatService via WorkOrderService."""

    def __init__(self, max_note_chars: int = 2000, max_reason_chars: int = 500):
        self.max_note_chars = max_note_chars
        self.max_reason_chars = max_reason_chars

    def parse(self, call_id: str, name: str, raw_arguments: str | dict[str, Any]) -> ParsedCall | ToolResult:
        if name not in ARG_MODELS:
            return ToolResult.fail(ErrorCode.UNKNOWN_TOOL, f"Unknown tool '{name[:60]}'. Nothing was executed.")
        if isinstance(raw_arguments, dict):  # some SDKs hand us parsed dicts (Anthropic)
            raw_arguments = json.dumps(raw_arguments)
        if not isinstance(raw_arguments, str):
            return ToolResult.fail(ErrorCode.INVALID_ARGUMENTS, "Tool arguments must be a JSON object.")
        if len(raw_arguments.encode("utf-8")) > MAX_RAW_TOOL_ARGS_BYTES:
            return ToolResult.fail(ErrorCode.INVALID_ARGUMENTS, "Tool arguments are too large.")
        try:
            decoded = strict_json_loads(raw_arguments or "{}")
        except _DuplicateKey as exc:
            return ToolResult.fail(ErrorCode.INVALID_ARGUMENTS, f"Duplicate argument '{exc}'.")
        except ValueError:
            return ToolResult.fail(ErrorCode.INVALID_ARGUMENTS, "Tool arguments are not valid JSON.")
        if not isinstance(decoded, dict):
            return ToolResult.fail(ErrorCode.INVALID_ARGUMENTS, "Tool arguments must be a JSON object.")
        try:
            args = ARG_MODELS[name].model_validate(decoded)
        except ValidationError as exc:
            fields = sorted({".".join(str(p) for p in e["loc"]) or "arguments" for e in exc.errors()})
            return ToolResult.fail(ErrorCode.INVALID_ARGUMENTS,
                                   f"Invalid arguments for {name}: {', '.join(fields)}.")
        if isinstance(args, AddNoteArgs) and len(args.text) > self.max_note_chars:
            return ToolResult.fail(ErrorCode.INVALID_ARGUMENTS, f"Notes are limited to {self.max_note_chars} characters.")
        if isinstance(args, EscalateArgs) and len(args.reason) > self.max_reason_chars:
            return ToolResult.fail(ErrorCode.INVALID_ARGUMENTS,
                                   f"Escalation reasons are limited to {self.max_reason_chars} characters.")
        return ParsedCall(call_id=call_id, name=name, args=args)


# ---- model-facing schemas ------------------------------------------------------------------

def _id_schema() -> dict[str, Any]:
    return {"type": "string", "pattern": WORK_ORDER_ID_PATTERN, "description": "Work order ID, e.g. WO-003"}


def tool_specs(max_note_chars: int = 2000, max_reason_chars: int = 500) -> list[dict[str, Any]]:
    """Provider-neutral specs: {name, description, parameters (JSON Schema)}.

    Hand-written to stay inside the JSON-Schema subset every provider's strict mode
    accepts; ``tests/test_tools.py`` proves each schema agrees with its validator.
    """
    obj = lambda props: {  # noqa: E731
        "type": "object", "properties": props, "required": list(props), "additionalProperties": False,
    }
    params = {
        "get_work_order": obj({"id": _id_schema()}),
        "update_status": obj({"id": _id_schema(), "status": {"type": "string", "enum": list(STATUS_VALUES)}}),
        "add_note": obj({"id": _id_schema(), "text": {"type": "string", "description": f"Technician's note, 1-{max_note_chars} chars"}}),
        "escalate": obj({"id": _id_schema(), "reason": {"type": "string", "description": f"Technician's reason, 1-{max_reason_chars} chars"}}),
        RESPOND_TOOL: obj({
            "kind": {"type": "string", "enum": ["answer", "clarify", "unsupported", "refuse"]},
            "text": {"type": "string", "description": "Reply shown to the technician (<=1200 chars)."},
            "citations": {
                "type": "array",
                "description": "Knowledge-base evidence: exact verbatim quotes copied from the cited section.",
                "items": obj({
                    "section_id": {"type": "string", "description": "kb-1 .. kb-5"},
                    "quote": {"type": "string", "description": "Exact text copied from that section"},
                }),
            },
            "missing": {"type": "array", "items": {"type": "string"},
                        "description": "Exact parts of the question the knowledge base does not cover."},
        }),
    }
    return [{"name": n, "description": DESCRIPTIONS[n], "parameters": params[n]}
            for n in (*BUSINESS_TOOLS, RESPOND_TOOL)]
