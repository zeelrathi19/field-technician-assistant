"""Provider-neutral model boundary. Provider SDK types never leave ``app/llm``."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

Role = Literal["user", "assistant", "tool", "context"]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON text exactly as the provider produced it


@dataclass(frozen=True)
class ModelMessage:
    """``context`` = server-authored per-turn data (focus, roster). Adapters map it to a
    system/developer slot so it can never be confused with the technician's words."""

    role: Role
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None
    tool_name: str | None = None


@dataclass(frozen=True)
class ModelUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class ModelDecision:
    tool_calls: tuple[ToolCall, ...]
    text: str = ""
    finish_reason: str = ""
    usage: ModelUsage = field(default_factory=ModelUsage)


class ModelError(Exception):
    """transient=True -> one bounded retry is allowed (before any write)."""

    def __init__(self, message: str, *, transient: bool, kind: str = "provider"):
        super().__init__(message)
        self.transient = transient
        self.kind = kind


class ModelClient(Protocol):
    provider: str
    model: str
    is_llm: bool

    def generate(
        self,
        system: str,
        messages: list[ModelMessage],
        tools: list[dict[str, Any]],
        *,
        max_output_tokens: int,
        timeout: float,
    ) -> ModelDecision: ...
