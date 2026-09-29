"""Google Gemini adapter using the native `generateContent` REST API.

Why not the OpenAI-compatible endpoint: Google AI Studio now issues "Auth" keys
(prefix `AQ.`) that must be sent as `x-goog-api-key`. The OpenAI-compatible route
sends `Authorization: Bearer`, which such keys often fail (400/401/404). The native
route works with both `AQ.` and legacy `AIza` keys.

* Function calling mode `ANY` restricted to the offered tools = the equivalent of
  `tool_choice=required`; the model must pick exactly one tool per step.
* Schemas are sent in the OpenAPI subset Gemini's `parameters` field accepts
  (no `additionalProperties`/`pattern`). The server still validates every call with
  the strict Pydantic models, so nothing is loosened where it matters.
* Thinking is switched off in code (`THINKING_BUDGET = 0`), never via `.env` or the prompt:
  tool picking is checked deterministically server-side, so the model does not need to
  reason at length. Gemini counts thought tokens against `maxOutputTokens`, and some 3.x
  flash models still think a little at budget 0 (~200 tokens seen on gemini-3.8-flash).
  A fixed `THINKING_HEADROOM` is added so `max_output_tokens` stays the reply budget; without
  it a 1024 budget left ~40 tokens for the call and live runs hit MALFORMED_FUNCTION_CALL.
* Thought signatures and part metadata the API returns are kept inside this adapter
  and replayed on the follow-up request, as Gemini requires for multi-step tool use.
"""

from __future__ import annotations

import itertools
import json
import threading
from collections import OrderedDict
from typing import Any

import httpx

from .base import ModelDecision, ModelError, ModelMessage, ModelUsage, ToolCall
from .errors import redact

DEFAULT_BASE = "https://generativelanguage.googleapis.com/v1beta"
_DROP = {"additionalProperties", "pattern", "$schema"}
THINKING_BUDGET = 0  # thinking off; the lowest value every Gemini flash model accepts
THINKING_HEADROOM = 512  # tokens reserved for residual thinking on top of max_output_tokens


def to_gemini_schema(schema: Any) -> Any:
    if isinstance(schema, dict):
        return {k: to_gemini_schema(v) for k, v in schema.items() if k not in _DROP}
    if isinstance(schema, list):
        return [to_gemini_schema(v) for v in schema]
    return schema


class GeminiClient:
    provider = "gemini"
    is_llm = True

    def __init__(self, model: str, api_key: str, base_url: str = "", temperature: float | None = None,
                 http_client: httpx.Client | None = None):
        self.model = model.removeprefix("models/")
        self.temperature = temperature
        self._base = (base_url or DEFAULT_BASE).rstrip("/")
        if self._base.endswith("/openai"):  # tolerate the OpenAI-compat URL from an older .env
            self._base = self._base[: -len("/openai")]
        self._key = api_key
        self._http = http_client or httpx.Client()
        self._ids = itertools.count(1)
        self._parts: OrderedDict[str, dict[str, Any]] = OrderedDict()  # call id -> original functionCall part
        self._lock = threading.Lock()

    # ---- request building ---------------------------------------------------------------------
    def _remember(self, call_id: str, part: dict[str, Any]) -> None:
        with self._lock:
            self._parts[call_id] = part
            while len(self._parts) > 2000:
                self._parts.popitem(last=False)

    def _call_part(self, call: ToolCall) -> dict[str, Any]:
        with self._lock:
            original = self._parts.get(call.id)
        if original is not None:
            return original  # includes thoughtSignature when the model produced one
        try:
            args = json.loads(call.arguments or "{}")
        except ValueError:
            args = {}
        return {"functionCall": {"name": call.name, "args": args if isinstance(args, dict) else {}}}

    def build_request(self, system: str, messages: list[ModelMessage], tools: list[dict[str, Any]],
                      max_output_tokens: int) -> dict[str, Any]:
        context: list[str] = []
        contents: list[dict[str, Any]] = []

        def push(role: str, part: dict[str, Any]) -> None:
            if contents and contents[-1]["role"] == role:
                contents[-1]["parts"].append(part)
            else:
                contents.append({"role": role, "parts": [part]})

        for m in messages:
            if m.role == "context":
                context.append(m.content)
            elif m.role == "user":
                push("user", {"text": m.content})
            elif m.role == "assistant":
                if m.content:
                    push("model", {"text": m.content})
                for c in m.tool_calls:
                    push("model", self._call_part(c))
            elif m.role == "tool":
                try:
                    result: Any = json.loads(m.content)
                except ValueError:
                    result = {"text": m.content}
                push("user", {"functionResponse": {"name": m.tool_name or "tool", "response": {"result": result}}})

        body: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system}] + [{"text": c} for c in context]},
            "contents": contents,
            "tools": [{"functionDeclarations": [
                {"name": t["name"], "description": t["description"], "parameters": to_gemini_schema(t["parameters"])}
                for t in tools]}],
            "toolConfig": {"functionCallingConfig": {"mode": "ANY", "allowedFunctionNames": [t["name"] for t in tools]}},
            "generationConfig": {"maxOutputTokens": max_output_tokens + THINKING_HEADROOM,
                                 "thinkingConfig": {"thinkingBudget": THINKING_BUDGET}},
        }
        if self.temperature is not None:
            body["generationConfig"]["temperature"] = self.temperature
        return body

    # ---- call -------------------------------------------------------------------------------------
    def generate(self, system: str, messages: list[ModelMessage], tools: list[dict[str, Any]], *,
                 max_output_tokens: int, timeout: float) -> ModelDecision:
        body = self.build_request(system, messages, tools, max_output_tokens)
        url = f"{self._base}/models/{self.model}:generateContent"
        try:
            resp = self._http.post(url, json=body, timeout=timeout,
                                   headers={"x-goog-api-key": self._key, "Content-Type": "application/json"})
        except httpx.TimeoutException as exc:
            raise ModelError("gemini timeout", transient=True) from exc
        except httpx.HTTPError as exc:
            raise ModelError(f"gemini connection error: {type(exc).__name__}", transient=True) from exc

        if resp.status_code != 200:
            try:
                err = resp.json().get("error", {})
                msg = f"{resp.status_code} {err.get('status', '')}: {err.get('message', '')}"
            except ValueError:
                msg = f"{resp.status_code}: {resp.text[:200]}"
            msg = redact(" ".join(msg.split()))[:300]
            transient = resp.status_code in (408, 429) or resp.status_code >= 500
            raise ModelError(f"gemini rejected request ({msg})" if not transient else f"gemini unavailable ({msg})",
                             transient=transient, kind="provider" if transient else "config")

        data = resp.json()
        usage_raw = data.get("usageMetadata") or {}
        usage = ModelUsage(usage_raw.get("promptTokenCount"), usage_raw.get("candidatesTokenCount"))
        candidates = data.get("candidates") or []
        if not candidates:
            reason = (data.get("promptFeedback") or {}).get("blockReason", "no candidates")
            return ModelDecision((), "", f"blocked:{reason}", usage)
        cand = candidates[0]
        calls: list[ToolCall] = []
        texts: list[str] = []
        for part in (cand.get("content") or {}).get("parts") or []:
            fc = part.get("functionCall")
            if fc:
                call_id = fc.get("id") or f"gemini_{next(self._ids)}"
                self._remember(call_id, part)
                calls.append(ToolCall(call_id, str(fc.get("name", "")), json.dumps(fc.get("args") or {})))
            elif isinstance(part.get("text"), str) and not part.get("thought"):
                texts.append(part["text"])
        return ModelDecision(tuple(calls), "".join(texts), str(cand.get("finishReason", "")), usage)
