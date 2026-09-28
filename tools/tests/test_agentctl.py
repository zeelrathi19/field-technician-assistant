"""agentctl behaviour in a throwaway git repo (two agents, two worktrees)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2]


def run(cwd: Path, *args: str, ok: bool = True) -> subprocess.CompletedProcess:
    p = subprocess.run([sys.executable, str(cwd / "tools" / "agentctl.py"), *args], cwd=cwd, capture_output=True, text=True)
    if ok:
        assert p.returncode == 0, p.stderr
    return p


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    (r / "tools").mkdir(parents=True)
    shutil.copy(SRC / "tools" / "agentctl.py", r / "tools")
    shutil.copy(SRC / "AGENTS.md", r)
    tasks = r / ".agents" / "tasks"
    tasks.mkdir(parents=True)
    card = "---\nid: {id}\ntitle: {id} work\nstatus: {st}\npriority: P1\nowner:\ndepends_on: [{deps}]\npaths: [{paths}]\n---\n"
    (tasks / "A.md").write_text(card.format(id="A", st="todo", deps="", paths="backend/app/llm/**"))
    (tasks / "B.md").write_text(card.format(id="B", st="todo", deps="", paths="backend/app/llm/gemini.py"))
    (tasks / "C.md").write_text(card.format(id="C", st="todo", deps="A", paths="frontend/**"))
    (tasks / "D.md").write_text(card.format(id="D", st="todo", deps="", paths="docs/**"))
    git(r, "init", "-q", "-b", "main")
    git(r, "config", "user.name", "Zeel Rathi")
    git(r, "config", "user.email", "z@example.invalid")
    run(r, "sync-pointers")
    git(r, "add", "-A")
    git(r, "commit", "-qm", "init")
    return r


def test_claim_is_exclusive(repo):
    run(repo, "claim", "A", "--agent", "codex-1", "--provider", "openai")
    p = run(repo, "claim", "A", "--agent", "claude-1", ok=False)
    assert p.returncode == 1 and "claimed by codex-1" in p.stderr


def test_path_overlap_blocks_second_agent(repo):
    run(repo, "claim", "A", "--agent", "codex-1")
    p = run(repo, "claim", "B", "--agent", "gemini-1", ok=False)
    assert "path overlap" in p.stderr
    run(repo, "claim", "D", "--agent", "gemini-1")  # disjoint paths are fine


def test_dependencies_enforced(repo):
    p = run(repo, "claim", "C", "--agent", "codex-1", ok=False)
    assert "depends on unfinished A" in p.stderr


def test_claims_shared_across_worktrees(repo):
    out = run(repo, "worktree", "A", "--agent", "codex-1").stdout
    wt = Path(out.split("cd ")[1].split()[0])
    assert wt.exists() and git(wt, "branch", "--show-current") == "agent/codex-1/A"
    p = run(wt, "claim", "A", "--agent", "claude-2", ok=False)  # seen from inside the other worktree
    assert "claimed by codex-1" in p.stderr
    ctx = run(repo, "context").stdout
    assert "A: codex-1" in ctx and "D " in ctx


def test_release_updates_card_and_handoff(repo):
    run(repo, "claim", "D", "--agent", "gemini-1")
    run(repo, "handoff", "D", "--agent", "gemini-1", "--summary", "did docs", "--checks", "make check: ok")
    run(repo, "release", "D", "--agent", "gemini-1", "--status", "review")
    card = (repo / ".agents" / "tasks" / "D.md").read_text()
    assert "status: review" in card and "owner: gemini-1" in card
    assert any((repo / ".agents" / "handoffs").glob("*-D-gemini-1.md"))
    events = (Path(git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir")) / "agentctl" / "events.jsonl").read_text()
    assert '"event": "claim"' in events and '"event": "release"' in events


def test_stale_claim_takeover_requires_force(repo):
    run(repo, "claim", "A", "--agent", "codex-1")
    claim = Path(git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir")) / "agentctl" / "claims" / "A.json"
    data = json.loads(claim.read_text())
    data["heartbeat_at"] = "2000-01-01T00:00:00+00:00"
    claim.write_text(json.dumps(data))
    assert "stale" in run(repo, "claim", "A", "--agent", "claude-1", ok=False).stderr
    run(repo, "claim", "A", "--agent", "claude-1", "--force")


def test_check_paths_blocks_files_owned_by_other_live_claim(repo):
    run(repo, "claim", "A", "--agent", "codex-1")
    run(repo, "claim", "D", "--agent", "gemini-1")
    (repo / "backend" / "app" / "llm").mkdir(parents=True)
    (repo / "backend" / "app" / "llm" / "x.py").write_text("x = 1\n")
    git(repo, "add", "backend/app/llm/x.py")
    p = run(repo, "check-paths", "--staged", "--agent", "gemini-1", ok=False)
    assert "owned by A/codex-1" in p.stderr
    run(repo, "check-paths", "--staged", "--agent", "codex-1")


def test_doctor_detects_pointer_drift(repo):
    run(repo, "doctor")
    (repo / "CLAUDE.md").write_text("hand edited")
    assert "out of sync" in run(repo, "doctor", ok=False).stderr


def test_pointers_carry_invariants(repo):
    text = (repo / ".cursor" / "rules" / "agents.mdc").read_text()
    assert text.startswith("---\ndescription:") and "alwaysApply: true" in text and "Open -> In Progress" in text
    assert (repo / "CLAUDE.md").read_text().startswith("@AGENTS.md")
