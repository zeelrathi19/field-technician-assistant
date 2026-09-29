"""Anthropic Messages API adapter (native tool_use / tool_result blocks)."""

from __future__ import annotations

import json
from typing import Any

import anthropic


from .base import ModelDecision, ModelError, ModelMessage, ModelUsage, ToolCall
from .errors import detail


class AnthropicClient:
    provider = "anthropic"
    is_llm = True

    def __init__(self, model: str, api_key: str, base_url: str = "", temperature: float | None = None,
                 http_client: Any = None):
        self.model = model
        self.temperature = temperature
        self._client = anthropic.Anthropic(api_key=api_key, base_url=base_url or None, max_retries=0,
                                           http_client=http_client)

    @staticmethod
    def _convert(messages: list[ModelMessage]) -> tuple[list[str], list[dict[str, Any]]]:
        context: list[str] = []
        out: list[dict[str, Any]] = []

        def push(role: str, block: dict[str, Any]) -> None:
            if out and out[-1]["role"] == role:
                out[-1]["content"].append(block)
            else:
                out.append({"role": role, "content": [block]})

        for m in messages:
            if m.role == "context":
                context.append(m.content)
            elif m.role == "user":
                push("user", {"type": "text", "text": m.content})
            elif m.role == "assistant":
                if m.content:
                    push("assistant", {"type": "text", "text": m.content})
                for c in m.tool_calls:
                    try:
                        args = json.loads(c.arguments or "{}")
                    except ValueError:
                        args = {}
                    push("assistant", {"type": "tool_use", "id": c.id, "name": c.name,
                                       "input": args if isinstance(args, dict) else {}})
            elif m.role == "tool":
                push("user", {"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content})
        return context, out

    def generate(self, system: str, messages: list[ModelMessage], tools: list[dict[str, Any]], *,
                 max_output_tokens: int, timeout: float) -> ModelDecision:
        context, converted = self._convert(messages)
        system_blocks: list[dict[str, Any]] = [
            {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        system_blocks += [{"type": "text", "text": c} for c in context]
        kwargs: dict[str, Any] = {
            "model": self.model,
            "system": system_blocks,
            "messages": converted,
            "tools": [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]}
                      for t in tools],
            "tool_choice": {"type": "any", "disable_parallel_tool_use": True},
            "max_tokens": max_output_tokens,
            "timeout": timeout,
        }
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        try:
            resp = self._client.messages.create(**kwargs)
        except (anthropic.APITimeoutError, anthropic.APIConnectionError, anthropic.RateLimitError,
                anthropic.InternalServerError) as exc:
            raise ModelError(type(exc).__name__, transient=True) from exc
        except anthropic.AuthenticationError as exc:
            raise ModelError(f"provider authentication failed, check MODEL_API_KEY ({detail(exc)})", transient=False, kind="config") from exc
        except (anthropic.BadRequestError, anthropic.NotFoundError, anthropic.PermissionDeniedError,
                anthropic.UnprocessableEntityError) as exc:
            raise ModelError(f"provider rejected request: {type(exc).__name__} ({detail(exc)})", transient=False, kind="config") from exc
        except anthropic.APIStatusError as exc:
            raise ModelError(type(exc).__name__, transient=exc.status_code >= 500) from exc
        calls = tuple(ToolCall(id=b.id, name=b.name, arguments=json.dumps(b.input))
                      for b in resp.content if b.type == "tool_use")
        text = "".join(b.text for b in resp.content if b.type == "text")
        usage = ModelUsage(resp.usage.input_tokens, resp.usage.output_tokens) if resp.usage else ModelUsage()
        return ModelDecision(calls, text, resp.stop_reason or "", usage)
