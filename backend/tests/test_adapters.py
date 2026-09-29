"""Adapter contract tests against recorded wire shapes (no network, no key).

They prove request translation (tools, tool_choice, parallel control, message
roles, tool-result correlation) and response/error normalisation. They do not
prove a live model behaves well — that is `make smoke`.
"""

import json

import httpx
import pytest

from app.llm.base import ModelError, ModelMessage, ToolCall
from app.llm.openai_compat import OpenAICompatClient
from app.tools import tool_specs

HISTORY = [
    ModelMessage("user", "Show WO-003"),
    ModelMessage("assistant", "WO-003 is On Hold."),
    ModelMessage("context", "<server_context>{}</server_context>"),
    ModelMessage("user", "Mark it complete"),
    ModelMessage("assistant", "", tool_calls=(ToolCall("call_1", "get_work_order", '{"id":"WO-003"}'),)),
    ModelMessage("tool", '{"ok":true}', tool_call_id="call_1", tool_name="get_work_order"),
]


def transport(captured, status=200, payload=None):
    def handler(request):
        captured.append(json.loads(request.content))
        return httpx.Response(status, json=payload or {})
    return httpx.MockTransport(handler)


OPENAI_OK = {
    "id": "chatcmpl-1", "object": "chat.completion", "created": 1, "model": "m",
    "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
        "role": "assistant", "content": None,
        "tool_calls": [{"id": "call_2", "type": "function",
                        "function": {"name": "update_status", "arguments": "{\"id\":\"WO-003\",\"status\":\"Completed\"}"}}]}}],
    "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
}


def test_openai_request_and_response_shape():
    cap = []
    c = OpenAICompatClient("gpt-test", "sk-test", http_client=httpx.Client(transport=transport(cap, payload=OPENAI_OK)))
    d = c.generate("SYSTEM", HISTORY, tool_specs(), max_output_tokens=512, timeout=5)
    req = cap[0]
    assert req["tool_choice"] == "required" and req["parallel_tool_calls"] is False
    assert req["max_completion_tokens"] == 512
    assert all(t["function"]["strict"] is True for t in req["tools"])
    assert [t["function"]["name"] for t in req["tools"]] == ["get_work_order", "update_status", "add_note", "escalate", "respond"]
    roles = [m["role"] for m in req["messages"]]
    assert roles == ["system", "user", "assistant", "system", "user", "assistant", "tool"]
    assert req["messages"][5]["tool_calls"][0]["id"] == "call_1" and req["messages"][6]["tool_call_id"] == "call_1"
    assert d.tool_calls[0].name == "update_status" and json.loads(d.tool_calls[0].arguments)["status"] == "Completed"
    assert d.usage.input_tokens == 100


def test_openai_generic_compat_drops_unsupported_params():
    cap = []
    c = OpenAICompatClient("llama3.1", "", base_url="http://localhost:11434/v1", compat="generic",
                           http_client=httpx.Client(transport=transport(cap, payload=OPENAI_OK)))
    c.generate("S", HISTORY[:1], tool_specs(), max_output_tokens=256, timeout=5)
    req = cap[0]
    assert "parallel_tool_calls" not in req and "max_completion_tokens" not in req and req["max_tokens"] == 256
    assert all("strict" not in t["function"] for t in req["tools"])


@pytest.mark.parametrize("status,transient,kind", [(500, True, "provider"), (429, True, "provider"),
                                                   (401, False, "config"), (400, False, "config")])
def test_openai_error_mapping(status, transient, kind):
    c = OpenAICompatClient("m", "k", http_client=httpx.Client(transport=transport([], status, {"error": {"message": "x"}})))
    with pytest.raises(ModelError) as exc:
        c.generate("S", HISTORY[:1], tool_specs(), max_output_tokens=256, timeout=5)
    assert exc.value.transient is transient and exc.value.kind == kind

