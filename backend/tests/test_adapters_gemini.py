"""Native Gemini adapter: wire shape, AQ.-key header auth, thought-signature replay,
error mapping, and a full pipeline run against recorded generateContent responses."""

import json

import httpx
import pytest

from app.config import Settings
from app.llm.base import ModelError, ModelMessage, ToolCall
from app.llm.gemini_native import THINKING_BUDGET, THINKING_HEADROOM, GeminiClient, to_gemini_schema
from app.tools import tool_specs
from tests.harness import Harness

KEY = "AQ.Ab8RN6I" + "x" * 40


def fc_response(name, args, sig=None, text=None):
    part = {"functionCall": {"name": name, "args": args}}
    if sig:
        part["thoughtSignature"] = sig
    parts = ([{"text": text}] if text else []) + [part]
    return {"candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 1200, "candidatesTokenCount": 30}}


def mock(responses, seen):
    queue = list(responses)

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append({"url": str(req.url), "headers": dict(req.headers), "body": json.loads(req.content)})
        status, payload = queue.pop(0)
        return httpx.Response(status, json=payload)
    return httpx.Client(transport=httpx.MockTransport(handler))


HISTORY = [
    ModelMessage("user", "Show WO-003"),
    ModelMessage("assistant", "WO-003 is On Hold."),
    ModelMessage("context", "<server_context>{}</server_context>"),
    ModelMessage("user", "Mark it complete"),
]


def test_request_shape_and_header_auth():
    seen: list = []
    c = GeminiClient("models/gemini-2.5-flash", KEY, http_client=mock([(200, fc_response("respond", {"kind": "answer", "text": "hi", "citations": [], "missing": []}))], seen))
    d = c.generate("SYSTEM", HISTORY, tool_specs(), max_output_tokens=512, timeout=5)
    req = seen[0]
    assert req["url"].endswith("/v1beta/models/gemini-2.5-flash:generateContent")
    assert req["headers"]["x-goog-api-key"] == KEY and "authorization" not in req["headers"]
    body = req["body"]
    assert body["systemInstruction"]["parts"][0]["text"] == "SYSTEM" and "server_context" in body["systemInstruction"]["parts"][1]["text"]
    assert [c["role"] for c in body["contents"]] == ["user", "model", "user"]
    assert body["toolConfig"]["functionCallingConfig"]["mode"] == "ANY"
    assert body["toolConfig"]["functionCallingConfig"]["allowedFunctionNames"] == [t["name"] for t in tool_specs()]
    decls = body["tools"][0]["functionDeclarations"]
    assert "additionalProperties" not in json.dumps(decls) and "pattern" not in json.dumps(decls)
    assert body["generationConfig"]["maxOutputTokens"] == 512 + THINKING_HEADROOM
    assert d.tool_calls[0].name == "respond" and d.usage.input_tokens == 1200


def test_openai_compat_base_url_is_tolerated():
    seen: list = []
    c = GeminiClient("gemini-2.5-flash", KEY, base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                     http_client=mock([(200, fc_response("respond", {}))], seen))
    c.generate("S", HISTORY[:1], tool_specs(), max_output_tokens=256, timeout=5)
    assert "/openai" not in seen[0]["url"]


def test_thought_signature_and_tool_result_are_replayed():
    seen: list = []
    c = GeminiClient("gemini-x", KEY, http_client=mock([
        (200, fc_response("get_work_order", {"id": "WO-003"}, sig="SIG123", text="thinking out loud")),
        (200, fc_response("respond", {"kind": "answer", "text": "ok", "citations": [], "missing": []})),
    ], seen))
    first = c.generate("S", HISTORY[:1], tool_specs(), max_output_tokens=256, timeout=5)
    call = first.tool_calls[0]
    follow = HISTORY[:1] + [ModelMessage("assistant", "", tool_calls=(call,)),
                            ModelMessage("tool", '{"ok": true, "data": {"id": "WO-003"}}', tool_call_id=call.id, tool_name=call.name)]
    c.generate("S", follow, tool_specs(), max_output_tokens=256, timeout=5)
    contents = seen[1]["body"]["contents"]
    assert contents[1] == {"role": "model", "parts": [{"functionCall": {"name": "get_work_order", "args": {"id": "WO-003"}}, "thoughtSignature": "SIG123"}]}
    assert contents[2]["parts"][0]["functionResponse"] == {"name": "get_work_order", "response": {"result": {"ok": True, "data": {"id": "WO-003"}}}}


@pytest.mark.parametrize("status,transient,kind", [(404, False, "config"), (400, False, "config"), (401, False, "config"),
                                                   (403, False, "config"), (429, True, "provider"), (503, True, "provider")])
def test_error_mapping_includes_provider_message_without_key(status, transient, kind):
    payload = {"error": {"code": status, "status": "NOT_FOUND", "message": f"models/gemini-9 is not found; key={KEY}"}}
    c = GeminiClient("gemini-9", KEY, http_client=mock([(status, payload)], []))
    with pytest.raises(ModelError) as e:
        c.generate("S", HISTORY[:1], tool_specs(), max_output_tokens=256, timeout=5)
    assert e.value.transient is transient and e.value.kind == kind
    assert "gemini-9 is not found" in str(e.value) and KEY not in str(e.value)


def test_blocked_prompt_yields_no_tool_call():
    c = GeminiClient("g", KEY, http_client=mock([(200, {"promptFeedback": {"blockReason": "SAFETY"}})], []))
    d = c.generate("S", HISTORY[:1], tool_specs(), max_output_tokens=256, timeout=5)
    assert d.tool_calls == () and d.finish_reason == "blocked:SAFETY"


def test_schema_conversion_is_lossless_except_unsupported_keywords():
    spec = next(t for t in tool_specs() if t["name"] == "update_status")["parameters"]
    out = to_gemini_schema(spec)
    assert out["properties"]["status"]["enum"] == ["Open", "In Progress", "On Hold", "Completed"]
    assert out["required"] == ["id", "status"] and "additionalProperties" not in out


def test_settings_require_key_and_model():
    with pytest.raises(ValueError):
        Settings(model_provider="gemini", model_name="gemini-2.5-flash", model_api_key="")


def test_full_pipeline_with_recorded_gemini_responses(tmp_path):
    seen: list = []
    client = GeminiClient("gemini-2.5-flash", KEY, http_client=mock([
        (200, fc_response("get_work_order", {"id": "WO-003"}, sig="S1")),
        (200, fc_response("respond", {"kind": "answer", "text": "WO-003 is On Hold; next allowed status is Completed.", "citations": [], "missing": []})),
        (200, fc_response("update_status", {"id": "WO-003", "status": "Completed"})),
    ], seen))
    h = Harness(tmp_path, client)
    shown = h.say("Show WO-003")
    assert shown["reply"]["verified"] and shown["reply"]["text"].startswith("WO-003 is On Hold")
    done = h.say("Mark it complete")
    assert done["outcome"] == "acted" and h.status("WO-003") == "Completed"
    assert all(r["headers"]["x-goog-api-key"] == KEY for r in seen)


def test_thinking_is_off_and_cannot_eat_the_reply_budget():
    # Gemini 3.x flash thinks by default, and thought tokens count against maxOutputTokens:
    # a 1024 budget left ~40 tokens for the call and produced MALFORMED_FUNCTION_CALL live.
    seen: list = []
    c = GeminiClient("gemini-3.8-flash", KEY, http_client=mock([(200, fc_response("respond", {}))], seen))
    c.generate("S", HISTORY[:1], tool_specs(), max_output_tokens=1024, timeout=5)
    gen = seen[0]["body"]["generationConfig"]
    assert THINKING_BUDGET == 0
    assert gen["thinkingConfig"] == {"thinkingBudget": 0}
    assert gen["maxOutputTokens"] == 1024 + THINKING_HEADROOM and THINKING_HEADROOM > 0
