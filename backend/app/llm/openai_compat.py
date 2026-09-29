"""OpenAI Chat Completions adapter.

Works with api.openai.com and any OpenAI-compatible endpoint via MODEL_BASE_URL:
Gemini (generativelanguage.googleapis.com/v1beta/openai/), Groq, OpenRouter,
Together, DeepSeek, Mistral, Ollama, vLLM, LM Studio. ``compat=generic`` drops
parameters some compatible servers reject (strict schemas, parallel_tool_calls,
max_completion_tokens).
"""

from __future__ import annotations

from typing import Any

import httpx
import openai

from .base import ModelDecision, ModelError, ModelMessage, ModelUsage, ToolCall
from .errors import detail


class OpenAICompatClient:
    provider = "openai"
    is_llm = True

    def __init__(self, model: str, api_key: str, base_url: str = "", compat: str = "openai",
                 temperature: float | None = None, http_client: httpx.Client | None = None):
        self.model = model
        self.compat = compat
        self.temperature = temperature
        self._client = openai.OpenAI(
            api_key=api_key or "not-needed-for-local", base_url=base_url or None,
            max_retries=0,  # our turn budget owns retries
            http_client=http_client,
        )

    def _messages(self, system: str, messages: list[ModelMessage]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = [{"role": "system", "content": system}]
        for m in messages:
            if m.role == "context":
                out.append({"role": "system", "content": m.content})
            elif m.role == "user":
                out.append({"role": "user", "content": m.content})
            elif m.role == "assistant":
                msg: dict[str, Any] = {"role": "assistant", "content": m.content or None}
                if m.tool_calls:
                    msg["tool_calls"] = [
                        {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
                        for c in m.tool_calls
                    ]
                out.append(msg)
            elif m.role == "tool":
                out.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content})
        return out

    def _tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        strict = self.compat == "openai"
        out = []
        for t in tools:
            fn: dict[str, Any] = {"name": t["name"], "description": t["description"], "parameters": t["parameters"]}
            if strict:
                fn["strict"] = True
            out.append({"type": "function", "function": fn})
        return out

    def generate(self, system: str, messages: list[ModelMessage], tools: list[dict[str, Any]], *,
                 max_output_tokens: int, timeout: float) -> ModelDecision:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": self._messages(system, messages),
            "tools": self._tools(tools),
            "tool_choice": "required",
            "timeout": timeout,
        }
        if self.compat == "openai":
            kwargs["parallel_tool_calls"] = False
            kwargs["max_completion_tokens"] = max_output_tokens
        else:
            kwargs["max_tokens"] = max_output_tokens
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        try:
            resp = self._client.chat.completions.create(**kwargs)
        except (openai.APITimeoutError, openai.APIConnectionError, openai.RateLimitError,
                openai.InternalServerError) as exc:
            raise ModelError(f"{type(exc).__name__} ({detail(exc)})", transient=True) from exc
        except openai.AuthenticationError as exc:
            raise ModelError(f"provider authentication failed, check MODEL_API_KEY ({detail(exc)})", transient=False, kind="config") from exc
        except (openai.BadRequestError, openai.NotFoundError, openai.PermissionDeniedError,
                openai.UnprocessableEntityError) as exc:
            raise ModelError(f"provider rejected request: {type(exc).__name__} ({detail(exc)})", transient=False, kind="config") from exc
        except openai.APIError as exc:
            raise ModelError(f"{type(exc).__name__}", transient=False) from exc
        if not resp.choices:
            raise ModelError("empty response", transient=True)
        choice = resp.choices[0]
        calls = tuple(
            ToolCall(id=c.id, name=c.function.name, arguments=c.function.arguments or "")
            for c in (choice.message.tool_calls or [])
            if getattr(c, "type", "function") == "function"
        )
        usage = ModelUsage(getattr(resp.usage, "prompt_tokens", None), getattr(resp.usage, "completion_tokens", None)) \
            if resp.usage else ModelUsage()
        return ModelDecision(calls, choice.message.content or "", choice.finish_reason or "", usage)
