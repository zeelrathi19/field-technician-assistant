"""Codex CLI provider: argv/sandbox contract, output parsing, failure mapping, and a full
pipeline run through a fake `codex` executable (no Codex install or network needed)."""

import json
import subprocess
import sys
import textwrap

import pytest

from app.config import Settings
from app.llm.base import ModelError, ModelMessage
from app.llm.codex_cli import CodexCLIClient, output_schema
from app.main import create_app
from app.tools import tool_specs
from tests.harness import Harness


def fake_runner(reply: str | None, returncode: int = 0, stderr: str = "", seen: dict | None = None):
    def run(argv, input, capture_output, text, timeout, cwd, env):
        if seen is not None:
            seen.update(argv=argv, prompt=input, cwd=cwd)
        if reply is not None:
            out = argv[argv.index("-o") + 1]
            with open(out, "w") as fh:
                fh.write(reply)
        return subprocess.CompletedProcess(argv, returncode, "", stderr)
    return run


def test_argv_is_sandboxed_and_prompt_goes_via_stdin():
    seen: dict = {}
    c = CodexCLIClient("gpt-x", runner=fake_runner('{"tool":"respond","arguments_json":"{}"}', seen=seen))
    d = c.generate("SYSTEM", [ModelMessage("user", "Show WO-003")], tool_specs(), max_output_tokens=512, timeout=30)
    argv = seen["argv"]
    assert argv[:2] == ["codex", "exec"] and argv[argv.index("--sandbox") + 1] == "read-only"
    assert "--skip-git-repo-check" in argv and "--ephemeral" in argv and argv[-1] == "-"
    assert argv[argv.index("-C") + 1] == seen["cwd"] and argv[argv.index("-m") + 1] == "gpt-x"
    assert "Show WO-003" in seen["prompt"] and "SYSTEM" in seen["prompt"] and "Show WO-003" not in " ".join(argv)
    assert d.tool_calls[0].name == "respond"


def test_output_schema_forces_one_known_tool():
    s = output_schema(["get_work_order", "respond"])
    assert s["properties"]["tool"]["enum"] == ["get_work_order", "respond"] and s["additionalProperties"] is False


@pytest.mark.parametrize("reply", ["not json", '{"tool": 3, "arguments_json": "{}"}', '{"arguments_json": "{}"}', ""])
def test_unusable_output_yields_no_tool_call(reply):
    d = CodexCLIClient(runner=fake_runner(reply)).generate("S", [], tool_specs(), max_output_tokens=10, timeout=5)
    assert d.tool_calls == ()


def test_failures_map_to_model_errors():
    with pytest.raises(ModelError) as e:
        CodexCLIClient(runner=fake_runner(None, 1, "Error: not logged in")).generate("S", [], tool_specs(), max_output_tokens=10, timeout=5)
    assert e.value.kind == "config" and not e.value.transient

    def timeout(*a, **k):
        raise subprocess.TimeoutExpired("codex", 5)
    with pytest.raises(ModelError) as e:
        CodexCLIClient(runner=timeout).generate("S", [], tool_specs(), max_output_tokens=10, timeout=5)
    assert e.value.transient


FAKE_CODEX = textwrap.dedent('''\
    #!{python}
    import json, sys
    argv = sys.argv
    prompt = sys.stdin.read()
    block = prompt.split("CONVERSATION", 1)[1]
    convo = json.loads(block[block.index("\\n["):].rsplit("Choose exactly ONE", 1)[0])
    last = convo[-1]
    if last["role"] == "tool":
        choice = {{"tool": "respond", "arguments_json": json.dumps({{"kind": "answer", "text": "WO-003 is On Hold.", "citations": [], "missing": []}})}}
    elif "complete" in last["content"].lower():
        choice = {{"tool": "update_status", "arguments_json": json.dumps({{"id": "WO-003", "status": "Completed"}})}}
    else:
        choice = {{"tool": "get_work_order", "arguments_json": json.dumps({{"id": "WO-003"}})}}
    open(argv[argv.index("-o") + 1], "w").write(json.dumps(choice))
''')


def test_full_pipeline_through_fake_codex_binary(tmp_path):
    exe = tmp_path / "codex"
    exe.write_text(FAKE_CODEX.format(python=sys.executable))
    exe.chmod(0o755)
    h = Harness(tmp_path, model_provider="codex", codex_bin=str(exe))
    assert h.client.get("/api/meta").json()["provider"] == "codex"
    shown = h.say("Show WO-003")
    assert shown["reply"]["text"] == "WO-003 is On Hold." and shown["state"]["active_work_order_id"] == "WO-003"
    done = h.say("Mark it complete")
    assert done["outcome"] == "acted" and h.status("WO-003") == "Completed"


def test_missing_codex_binary_fails_startup(tmp_path):
    s = Settings(model_provider="codex", codex_bin=str(tmp_path / "nope"), database_path=tmp_path / "d.db")
    with pytest.raises(ValueError, match="codex"):
        create_app(s)
