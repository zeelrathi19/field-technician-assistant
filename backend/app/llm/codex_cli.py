"""Codex CLI adapter: use a locally signed-in `codex` (ChatGPT login) as the model.

For local testing without an API key. Each model call runs one non-interactive
`codex exec` in an empty temporary directory with a read-only sandbox, no session
persistence, and a JSON output schema that forces exactly one tool choice:

    {"tool": "<one of the offered tool names>", "arguments_json": "<JSON object as a string>"}

The server then treats that proposal exactly like a native tool call: registry,
strict schema, IntentGuard, WorkOrderService, AnswerVerifier. Codex never sees the
repository or the database and cannot act on its own.

Slower than an API (one CLI process per call); raise MODEL_TIMEOUT_SECONDS /
TURN_TIMEOUT_SECONDS accordingly. Not available inside the Docker image.
"""

from __future__ import annotations

import itertools
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .base import ModelDecision, ModelError, ModelMessage, ToolCall

Runner = Callable[..., subprocess.CompletedProcess]

PROTOCOL = """
You are acting as a function-calling model inside an application. You are NOT a coding agent here:
do not run shell commands, do not read or write files, do not browse. Only choose one function.

AVAILABLE FUNCTIONS (JSON Schema for each function's arguments):
{tools}

CONVERSATION (oldest first; roles: user, assistant, tool = result of an earlier function call, context = server data):
{conversation}

Choose exactly ONE function for the next step and reply with a JSON object:
{{"tool": "<function name>", "arguments_json": "<the function arguments as a JSON object, encoded as a string>"}}
"""


def output_schema(tool_names: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "tool": {"type": "string", "enum": tool_names},
            "arguments_json": {"type": "string"},
        },
        "required": ["tool", "arguments_json"],
        "additionalProperties": False,
    }


def render_conversation(messages: list[ModelMessage]) -> str:
    rows: list[dict[str, Any]] = []
    for m in messages:
        row: dict[str, Any] = {"role": m.role, "content": m.content}
        if m.tool_calls:
            row["function_calls"] = [{"id": c.id, "name": c.name, "arguments": c.arguments} for c in m.tool_calls]
        if m.tool_call_id:
            row["result_for"] = m.tool_call_id
        rows.append(row)
    return json.dumps(rows, indent=1, ensure_ascii=False)


class CodexCLIClient:
    provider = "codex"
    is_llm = True

    def __init__(self, model: str = "", binary: str = "codex", runner: Runner | None = None):
        self.model = model or "codex-default"
        self._model_flag = model
        self.binary = binary
        self._run = runner or subprocess.run
        self._ids = itertools.count(1)

    @staticmethod
    def available(binary: str) -> bool:
        return shutil.which(binary) is not None or Path(binary).is_file()

    def build_prompt(self, system: str, messages: list[ModelMessage], tools: list[dict[str, Any]]) -> str:
        specs = json.dumps([{"name": t["name"], "description": t["description"], "parameters": t["parameters"]}
                            for t in tools], indent=1)
        return f"<instructions>\n{system}\n</instructions>\n" + PROTOCOL.format(
            tools=specs, conversation=render_conversation(messages))

    def generate(self, system: str, messages: list[ModelMessage], tools: list[dict[str, Any]], *,
                 max_output_tokens: int, timeout: float) -> ModelDecision:
        prompt = self.build_prompt(system, messages, tools)
        names = [t["name"] for t in tools]
        with tempfile.TemporaryDirectory(prefix="fta-codex-") as tmp:
            schema_path = Path(tmp) / "schema.json"
            out_path = Path(tmp) / "last_message.json"
            schema_path.write_text(json.dumps(output_schema(names)), encoding="utf-8")
            argv = [self.binary, "exec", "--sandbox", "read-only", "--skip-git-repo-check", "--ephemeral",
                    "-C", tmp, "--output-schema", str(schema_path), "-o", str(out_path)]
            if self._model_flag:
                argv += ["-m", self._model_flag]
            argv.append("-")  # prompt on stdin (keeps it out of the process list)
            try:
                proc = self._run(argv, input=prompt, capture_output=True, text=True, timeout=timeout,
                                 cwd=tmp, env={**os.environ, "NO_COLOR": "1"})
            except FileNotFoundError as exc:
                raise ModelError(f"codex binary not found: {self.binary}", transient=False, kind="config") from exc
            except subprocess.TimeoutExpired as exc:
                raise ModelError("codex exec timed out", transient=True) from exc
            if proc.returncode != 0:
                err = (proc.stderr or "").lower()
                auth = any(w in err for w in ("login", "not logged", "unauthorized", "auth"))
                raise ModelError(f"codex exec failed (exit {proc.returncode})", transient=not auth,
                                 kind="config" if auth else "provider")
            raw = out_path.read_text(encoding="utf-8").strip() if out_path.exists() else (proc.stdout or "").strip()
        try:
            parsed = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
            name, args = parsed["tool"], parsed["arguments_json"]
        except (ValueError, KeyError, TypeError):
            # Unusable output = no tool call; ChatService fails closed and shows nothing unverified.
            return ModelDecision(tool_calls=(), text="", finish_reason="invalid_output")
        if not isinstance(name, str) or not isinstance(args, str):
            return ModelDecision(tool_calls=(), text="", finish_reason="invalid_output")
        return ModelDecision((ToolCall(f"codex_{next(self._ids)}", name, args),), finish_reason="tool_calls")
