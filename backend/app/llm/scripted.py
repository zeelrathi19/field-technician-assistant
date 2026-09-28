"""Deterministic test double: replays scripted decisions or a callable policy."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from .base import ModelDecision, ModelError, ModelMessage, ToolCall

Step = ModelDecision | ModelError | Callable[[list[ModelMessage]], ModelDecision]


def call(name: str, args: dict[str, Any] | str, call_id: str | None = None) -> ToolCall:
    raw = args if isinstance(args, str) else json.dumps(args)
    return ToolCall(id=call_id or f"call_{name}", name=name, arguments=raw)


def decide(*calls: ToolCall) -> ModelDecision:
    return ModelDecision(tool_calls=tuple(calls), finish_reason="tool_calls")


def respond(kind: str = "answer", text: str = "", citations: list[dict[str, str]] | None = None,
            missing: list[str] | None = None) -> ModelDecision:
    return decide(call("respond", {"kind": kind, "text": text, "citations": citations or [], "missing": missing or []}))


class ScriptedModel:
    provider = "scripted"
    model = "scripted-test"
    is_llm = False

    def __init__(self, steps: list[Step] | None = None):
        self.steps = list(steps or [])
        self.calls: list[list[ModelMessage]] = []

    def generate(self, system: str, messages: list[ModelMessage], tools: list[dict[str, Any]], *,
                 max_output_tokens: int, timeout: float) -> ModelDecision:
        self.calls.append(list(messages))
        if not self.steps:
            raise AssertionError("ScriptedModel ran out of steps")
        step = self.steps.pop(0)
        if isinstance(step, ModelError):
            raise step
        if callable(step) and not isinstance(step, ModelDecision):
            return step(messages)
        return step
