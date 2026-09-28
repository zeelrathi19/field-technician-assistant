"""Adapter contract tests against recorded wire shapes (no network, no key).

They prove request translation (tools, tool_choice, parallel control, message
roles, tool-result correlation) and response/error normalisation. They do not
prove a live model behaves well — that is `make smoke`.
"""

import json

import httpx
import httpx2
import pytest

from app.llm.anthropic_native import AnthropicClient
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


def transport(captured, status=200, payload=None, lib=httpx):
    def handler(request):
        captured.append(json.loads(request.content))
        return lib.Response(status, json=payload or {})
    return lib.MockTransport(handler)


def anthropic_http(captured, status=200, payload=None):
    # anthropic>=1.x ships on httpx2; openai still uses httpx
    return httpx2.Client(transport=transport(captured, status, payload, lib=httpx2))


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


ANTHROPIC_OK = {
    "id": "msg_1", "type": "message", "role": "assistant", "model": "m", "stop_reason": "tool_use",
    "content": [{"type": "tool_use", "id": "toolu_2", "name": "respond",
                 "input": {"kind": "answer", "text": "hi", "citations": [], "missing": []}}],
    "usage": {"input_tokens": 50, "output_tokens": 10},
}


def test_anthropic_request_and_response_shape():
    cap = []
    c = AnthropicClient("claude-test", "sk-ant-test", http_client=anthropic_http(cap, payload=ANTHROPIC_OK))
    d = c.generate("SYSTEM", HISTORY, tool_specs(), max_output_tokens=512, timeout=5)
    req = cap[0]
    assert req["tool_choice"] == {"type": "any", "disable_parallel_tool_use": True}
    assert req["system"][0]["text"] == "SYSTEM" and "server_context" in req["system"][1]["text"]
    assert [m["role"] for m in req["messages"]] == ["user", "assistant", "user", "assistant", "user"]
    tool_use = req["messages"][3]["content"][0]
    tool_result = req["messages"][4]["content"][0]
    assert tool_use["type"] == "tool_use" and tool_use["input"] == {"id": "WO-003"}
    assert tool_result == {"type": "tool_result", "tool_use_id": "call_1", "content": '{"ok":true}'}
    assert req["tools"][0]["input_schema"]["additionalProperties"] is False
    assert d.tool_calls[0].name == "respond" and json.loads(d.tool_calls[0].arguments)["kind"] == "answer"
    assert d.usage.output_tokens == 10


@pytest.mark.parametrize("status,transient", [(529, True), (500, True), (401, False)])
def test_anthropic_error_mapping(status, transient):
    body = {"type": "error", "error": {"type": "x", "message": "x"}}
    c = AnthropicClient("m", "k", http_client=anthropic_http([], status, body))
    with pytest.raises(ModelError) as exc:
        c.generate("S", HISTORY[:1], tool_specs(), max_output_tokens=256, timeout=5)
    assert exc.value.transient is transient
