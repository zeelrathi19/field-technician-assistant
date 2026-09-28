#!/usr/bin/env python3
"""agentctl — vendor-neutral coordination for many coding agents on one repo.

Any agent (Claude Code, Codex, Gemini CLI, Cursor, Copilot, Aider, Cline, Windsurf,
OpenCode, a human...) that can run a shell command can use it. Standard library
only; Python >= 3.9.

State model
-----------
* Durable plan  : .agents/tasks/*.md       (committed; status changes land via PR)
* Live claims   : <git-common-dir>/agentctl/claims/<TASK>.json
                  The git *common* dir is shared by every worktree of the clone, so
                  agents in parallel worktrees on one machine see each other's claims
                  instantly. Claims are created with O_CREAT|O_EXCL (atomic).
* Event log     : <git-common-dir>/agentctl/events.jsonl (append-only audit)
* Cross-machine : claim branches `agent/<agent>/<task>`; `claims` also lists remote ones.
* Handoffs      : .agents/handoffs/*.md    (committed)
* Learnings     : .agents/LEARNINGS.md     (committed, append-only)

Run `python3 tools/agentctl.py --help`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
AGENTS_DIR = ROOT / ".agents"
TASKS_DIR = AGENTS_DIR / "tasks"
HANDOFFS_DIR = AGENTS_DIR / "handoffs"
LEARNINGS = AGENTS_DIR / "LEARNINGS.md"
AGENTS_MD = ROOT / "AGENTS.md"
STALE_HOURS = 2.0
STATUSES = ("todo", "in_progress", "review", "done", "blocked")
REQUIRED_AUTHOR = "Zeel Rathi"

# Files generated from AGENTS.md so every tool's native instruction loader sees the same rules.
POINTERS: Dict[str, str] = {
    "CLAUDE.md": "md",                              # Claude Code (also supports @imports)
    "GEMINI.md": "md",                              # Gemini CLI
    ".github/copilot-instructions.md": "md",        # GitHub Copilot
    ".cursor/rules/agents.mdc": "mdc",              # Cursor
    ".windsurf/rules/agents.md": "md",              # Windsurf
    ".clinerules/agents.md": "md",                  # Cline / Roo
    "CONVENTIONS.md": "md",                         # Aider (see .aider.conf.yml)
}
BEGIN, END = "<!-- agentctl:invariants:begin -->", "<!-- agentctl:invariants:end -->"


# ---------------------------------------------------------------------------------- helpers
def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(t: Optional[dt.datetime] = None) -> str:
    return (t or now()).isoformat(timespec="seconds")


def git(*args: str, check: bool = False, cwd: Optional[Path] = None) -> str:
    try:
        out = subprocess.run(["git", *args], cwd=str(cwd or ROOT), capture_output=True, text=True, check=check)
    except FileNotFoundError:
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def state_dir() -> Path:
    common = git("rev-parse", "--path-format=absolute", "--git-common-dir")
    base = Path(common) / "agentctl" if common else AGENTS_DIR / ".local"
    (base / "claims").mkdir(parents=True, exist_ok=True)
    return base


def log_event(kind: str, **data: Any) -> None:
    with open(state_dir() / "events.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": iso(), "event": kind, **data}) + "\n")


def die(msg: str, code: int = 1) -> None:
    print(f"agentctl: {msg}", file=sys.stderr)
    sys.exit(code)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "x"


# ---------------------------------------------------------------------------------- tasks
def _parse_value(raw: str) -> Any:
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        return [v.strip().strip("'\"") for v in inner.split(",") if v.strip()] if inner else []
    return raw.strip("'\"")


def load_task(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        raise ValueError(f"{path.name}: missing front matter")
    meta: Dict[str, Any] = {}
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = _parse_value(value)
    meta.setdefault("depends_on", [])
    meta.setdefault("paths", [])
    meta.setdefault("owner", "")
    meta["body"] = m.group(2).strip()
    meta["file"] = path
    for req in ("id", "title", "status"):
        if not meta.get(req):
            raise ValueError(f"{path.name}: missing '{req}'")
    if meta["status"] not in STATUSES:
        raise ValueError(f"{path.name}: status must be one of {STATUSES}")
    return meta


def load_tasks() -> Dict[str, Dict[str, Any]]:
    tasks: Dict[str, Dict[str, Any]] = {}
    for p in sorted(TASKS_DIR.glob("*.md")):
        t = load_task(p)
        if t["id"] in tasks:
            raise ValueError(f"duplicate task id {t['id']}")
        tasks[t["id"]] = t
    return tasks


def set_task_field(task: Dict[str, Any], key: str, value: str) -> None:
    path: Path = task["file"]
    text = path.read_text(encoding="utf-8")
    head, sep, body = text[4:].partition("\n---")
    lines = head.splitlines()
    for i, line in enumerate(lines):
        if line.split(":", 1)[0].strip() == key:
            lines[i] = f"{key}: {value}"
            break
    else:
        lines.append(f"{key}: {value}")
    path.write_text("---\n" + "\n".join(lines) + sep + body, encoding="utf-8")


def _static_prefix(pattern: str) -> str:
    out = []
    for part in pattern.split("/"):
        if any(ch in part for ch in "*?["):
            break
        out.append(part)
    return "/".join(out)


def paths_overlap(a: List[str], b: List[str]) -> List[str]:
    hits = []
    for pa in a:
        for pb in b:
            sa, sb = _static_prefix(pa), _static_prefix(pb)
            if (fnmatch.fnmatch(pa, pb) or fnmatch.fnmatch(pb, pa) or sa == sb
                    or (sa and sb and (sa.startswith(sb.rstrip("/") + "/") or sb.startswith(sa.rstrip("/") + "/")))):
                hits.append(f"{pa} <-> {pb}")
    return hits


def path_owned(path: str, patterns: List[str]) -> bool:
    for pat in patterns:
        if fnmatch.fnmatch(path, pat) or path == pat.rstrip("/") or path.startswith(pat.rstrip("/*") + "/"):
            return True
    return False


# ---------------------------------------------------------------------------------- claims
def claim_path(task_id: str) -> Path:
    return state_dir() / "claims" / f"{task_id}.json"


def read_claims() -> Dict[str, Dict[str, Any]]:
    out = {}
    for p in (state_dir() / "claims").glob("*.json"):
        try:
            c = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        hb = dt.datetime.fromisoformat(c.get("heartbeat_at", c.get("claimed_at")))
        c["age_hours"] = (now() - hb).total_seconds() / 3600
        c["stale"] = c["age_hours"] > STALE_HOURS
        out[p.stem] = c
    return out


def remote_claim_branches() -> List[str]:
    out = git("branch", "-r", "--list", "*/agent/*")
    return [b.strip() for b in out.splitlines() if b.strip()]


def cmd_claim(args: argparse.Namespace) -> None:
    tasks = load_tasks()
    task = tasks.get(args.task) or die(f"unknown task {args.task}")
    assert task is not None
    if task["status"] == "done":
        die(f"{args.task} is already done")
    undone = [d for d in task["depends_on"] if tasks.get(d, {}).get("status") != "done"]
    if undone and not args.force:
        die(f"{args.task} depends on unfinished {', '.join(undone)} (use --force to override knowingly)")
    claims = read_claims()
    existing = claims.get(args.task)
    if existing and existing["agent"] != args.agent:
        if not (existing["stale"] and args.force):
            die(f"{args.task} is claimed by {existing['agent']} ({existing.get('provider') or '?'}) "
                f"{existing['age_hours']:.1f}h ago" + (" — stale; re-run with --force to take over" if existing["stale"] else ""))
        claim_path(args.task).unlink(missing_ok=True)
        log_event("takeover", task=args.task, agent=args.agent, previous=existing["agent"])
    for other_id, other in claims.items():
        if other_id == args.task or other["agent"] == args.agent or other["stale"]:
            continue
        hits = paths_overlap(task["paths"], tasks.get(other_id, {}).get("paths", []))
        if hits and not args.force:
            die(f"path overlap with {other_id} claimed by {other['agent']}: {hits[0]} (coordinate, or --force)")
    remote = [b for b in remote_claim_branches() if b.endswith(f"/{args.task}") and f"/agent/{args.agent}/" not in b]
    if remote and not args.force:
        die(f"another machine appears to hold {args.task}: {remote[0]} (use --force if abandoned)")
    record = {
        "task": args.task, "agent": args.agent, "provider": args.provider or "", "claimed_at": iso(),
        "heartbeat_at": iso(), "branch": git("branch", "--show-current"), "worktree": str(Path.cwd()),
        "note": args.note or "",
    }
    if existing and existing["agent"] == args.agent:
        record["claimed_at"] = existing["claimed_at"]
        claim_path(args.task).write_text(json.dumps(record, indent=1), encoding="utf-8")
        print(f"refreshed claim on {args.task} for {args.agent}")
        return
    try:
        fd = os.open(claim_path(args.task), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        die(f"{args.task} was claimed by someone else a moment ago; run `agentctl claims`")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=1)
    log_event("claim", task=args.task, agent=args.agent, provider=args.provider or "")
    print(f"claimed {args.task} ({task['title']}) for {args.agent}")
    print("owned paths: " + (", ".join(task["paths"]) or "(none declared)"))


def cmd_heartbeat(args: argparse.Namespace) -> None:
    p = claim_path(args.task)
    if not p.exists():
        die(f"no claim on {args.task}")
    c = json.loads(p.read_text(encoding="utf-8"))
    if c["agent"] != args.agent:
        die(f"{args.task} is claimed by {c['agent']}, not {args.agent}")
    c["heartbeat_at"] = iso()
    p.write_text(json.dumps(c, indent=1), encoding="utf-8")
    print(f"heartbeat {args.task}")


def cmd_release(args: argparse.Namespace) -> None:
    p = claim_path(args.task)
    if p.exists():
        c = json.loads(p.read_text(encoding="utf-8"))
        if c["agent"] != args.agent and not args.force:
            die(f"{args.task} is claimed by {c['agent']}; use --force to release someone else's claim")
        p.unlink()
    if args.status:
        tasks = load_tasks()
        if args.task in tasks:
            set_task_field(tasks[args.task], "status", args.status)
            set_task_field(tasks[args.task], "owner", args.agent if args.status in ("review", "done") else "")
    log_event("release", task=args.task, agent=args.agent, status=args.status or "")
    print(f"released {args.task}" + (f" -> {args.status} (commit .agents/tasks change)" if args.status else ""))


def cmd_claims(_: argparse.Namespace) -> None:
    claims = read_claims()
    if not claims:
        print("no active local claims")
    for tid, c in sorted(claims.items()):
        flag = "STALE" if c["stale"] else "live "
        print(f"{flag} {tid:6s} {c['agent']:<18s} {c.get('provider') or '-':<12s} {c['age_hours']:5.1f}h  "
              f"branch={c.get('branch') or '-'}  {c.get('worktree')}")
    remote = remote_claim_branches()
    if remote:
        print("remote claim branches: " + ", ".join(remote))


def cmd_worktree(args: argparse.Namespace) -> None:
    cmd_claim(args)
    branch = f"agent/{slug(args.agent)}/{args.task}"
    target = ROOT.parent / f"{ROOT.name}.worktrees" / f"{args.task}-{slug(args.agent)}"
    if target.exists():
        print(f"worktree exists: {target}")
    else:
        base = args.base or "main"
        res = subprocess.run(["git", "worktree", "add", "-b", branch, str(target), base], cwd=ROOT,
                             capture_output=True, text=True)
        if res.returncode != 0:
            res = subprocess.run(["git", "worktree", "add", str(target), branch], cwd=ROOT, capture_output=True, text=True)
        if res.returncode != 0:
            die(res.stderr.strip())
    c = json.loads(claim_path(args.task).read_text(encoding="utf-8"))
    c.update(branch=branch, worktree=str(target))
    claim_path(args.task).write_text(json.dumps(c, indent=1), encoding="utf-8")
    log_event("worktree", task=args.task, agent=args.agent, path=str(target), branch=branch)
    print(f"worktree ready: cd {target}   (branch {branch})")


# ---------------------------------------------------------------------------------- board / context
def cmd_board(args: argparse.Namespace) -> None:
    tasks = load_tasks()
    claims = read_claims()
    if args.json:
        print(json.dumps([{k: v for k, v in t.items() if k not in ("file", "body")} | {"claim": claims.get(t["id"])}
                          for t in tasks.values()], indent=1, default=str))
        return
    for t in tasks.values():
        c = claims.get(t["id"])
        who = f"claimed by {c['agent']}{' (STALE)' if c['stale'] else ''}" if c else (t["owner"] or "")
        deps = f" deps={','.join(t['depends_on'])}" if t["depends_on"] else ""
        print(f"{t['id']:6s} {t['status']:<11s} {t['title'][:58]:<58s} {who}{deps}")


def ready_tasks(tasks: Dict[str, Dict[str, Any]], claims: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for t in tasks.values():
        if t["status"] != "todo" or (t["id"] in claims and not claims[t["id"]]["stale"]):
            continue
        if any(tasks.get(d, {}).get("status") != "done" for d in t["depends_on"]):
            continue
        busy = [cid for cid, c in claims.items() if not c["stale"] and paths_overlap(t["paths"], tasks.get(cid, {}).get("paths", []))]
        if not busy:
            out.append(t)
    return sorted(out, key=lambda t: (t.get("priority", "P9"), t["id"]))


def invariants_block() -> str:
    text = AGENTS_MD.read_text(encoding="utf-8")
    if BEGIN not in text or END not in text:
        die("AGENTS.md is missing the invariants markers")
    return text.split(BEGIN, 1)[1].split(END, 1)[0].strip()


def cmd_context(args: argparse.Namespace) -> None:
    tasks = load_tasks()
    claims = read_claims()
    print("# Field Technician Assistant — agent context\n")
    print(f"repo: {ROOT}\nbranch: {git('branch', '--show-current') or '-'}   head: {git('log', '-1', '--format=%h %s') or '-'}")
    dirty = git("status", "--porcelain")
    print(f"working tree: {'dirty (' + str(len(dirty.splitlines())) + ' files)' if dirty else 'clean'}\n")
    print("## Read first\nAGENTS.md -> docs/architecture.md -> docs/contracts.md -> your task card in .agents/tasks/\n")
    print("## Invariants (from AGENTS.md)\n" + invariants_block() + "\n")
    counts: Dict[str, int] = {}
    for t in tasks.values():
        counts[t["status"]] = counts.get(t["status"], 0) + 1
    print("## Board  " + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    for t in tasks.values():
        if t["status"] != "done":
            c = claims.get(t["id"])
            print(f"- {t['id']} [{t['status']}] {t['title']}" + (f"  <- {c['agent']}" if c else ""))
    print("\n## Active claims")
    if not claims:
        print("- none")
    for tid, c in claims.items():
        print(f"- {tid}: {c['agent']} ({c.get('provider') or '?'}) {c['age_hours']:.1f}h{' STALE' if c['stale'] else ''} @ {c.get('branch')}")
    ready = ready_tasks(tasks, claims)
    print("\n## Ready to pick up (deps done, no path conflicts)")
    print("\n".join(f"- {t['id']} {t['title']}  paths={t['paths']}" for t in ready[:6]) or "- none")
    hand = sorted(HANDOFFS_DIR.glob("*.md"))[-5:] if HANDOFFS_DIR.exists() else []
    print("\n## Recent handoffs")
    print("\n".join(f"- .agents/handoffs/{h.name}" for h in hand) or "- none")
    if LEARNINGS.exists():
        entries = [ln for ln in LEARNINGS.read_text(encoding="utf-8").splitlines() if ln.startswith("- ")][-5:]
        print("\n## Recent learnings\n" + ("\n".join(entries) or "- none"))
    print("\n## Commands\nmake check | python3 tools/agentctl.py worktree <TASK> --agent <name> --provider <llm> | "
          "... handoff <TASK> --agent <name> --summary '...'")


# ---------------------------------------------------------------------------------- handoff / learn / new-task
def cmd_handoff(args: argparse.Namespace) -> None:
    HANDOFFS_DIR.mkdir(parents=True, exist_ok=True)
    base = args.base or "main"
    changed = git("diff", "--name-only", f"{base}...HEAD") or git("diff", "--name-only")
    stat = git("diff", "--stat", f"{base}...HEAD")
    name = f"{now().strftime('%Y-%m-%d-%H%M')}-{args.task}-{slug(args.agent)}.md"
    body = f"""# Handoff {args.task} — {args.agent}

- when: {iso()}
- agent / provider: {args.agent} / {args.provider or '-'}
- branch: {git('branch', '--show-current') or '-'}  head: {git('log', '-1', '--format=%h') or '-'}

## Summary
{args.summary}

## Files changed (vs {base})
{chr(10).join('- ' + f for f in changed.splitlines()) or '- (none)'}

## Checks actually run
{args.checks or '- (not stated — reviewer must run `make check`)'}

## Contract changes
{args.contracts or '- none'}

## Risks / open issues
{args.risks or '- none stated'}

## Next concrete action
{args.next or '- reviewer merges after `make check`'}

<details><summary>diff stat</summary>

```
{stat}
```
</details>
"""
    (HANDOFFS_DIR / name).write_text(body, encoding="utf-8")
    log_event("handoff", task=args.task, agent=args.agent, file=name)
    print(f"wrote .agents/handoffs/{name}")


def cmd_learn(args: argparse.Namespace) -> None:
    line = (f"- {now().date()} [{args.agent}] {args.observation.strip()} — evidence: {args.evidence.strip()} "
            f"— consequence: {args.consequence.strip()}" + (" (hypothesis)" if args.hypothesis else ""))
    with open(LEARNINGS, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    print("appended to .agents/LEARNINGS.md")


def cmd_new_task(args: argparse.Namespace) -> None:
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    tasks = load_tasks()
    if args.id in tasks:
        die(f"{args.id} exists")
    path = TASKS_DIR / f"{args.id}-{slug(args.title)}.md"
    path.write_text(
        f"---\nid: {args.id}\ntitle: {args.title}\nstatus: todo\npriority: {args.priority}\nowner:\n"
        f"depends_on: [{', '.join(args.deps or [])}]\npaths: [{', '.join(args.paths or [])}]\n---\n\n"
        f"## Goal\n{args.goal or args.title}\n\n## Acceptance\n- [ ] tests added and `make check` passes\n", encoding="utf-8")
    print(f"created {path.relative_to(ROOT)}")


# ---------------------------------------------------------------------------------- pointers / doctor / paths
def render_pointer(kind: str) -> str:
    header = ("GENERATED by `python3 tools/agentctl.py sync-pointers` from AGENTS.md — do not edit here.\n\n"
              "Read AGENTS.md in full before changing anything. It is the single source of truth for every agent "
              "and every LLM provider working on this repository.\n\n")
    core = header + "## Invariants\n\n" + invariants_block() + "\n\n## Start\n\n`make context` (or `python3 tools/agentctl.py context`) prints the live board, claims and handoffs.\n"
    if kind == "mdc":
        return "---\ndescription: Project rules (from AGENTS.md)\nalwaysApply: true\n---\n\n" + core + "\n@AGENTS.md\n"
    return "@AGENTS.md\n\n" + core


def cmd_sync_pointers(_: argparse.Namespace) -> None:
    for rel, kind in POINTERS.items():
        p = ROOT / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(render_pointer(kind), encoding="utf-8")
    print(f"synced {len(POINTERS)} pointer files")


def cmd_doctor(_: argparse.Namespace) -> None:
    problems: List[str] = []
    warnings: List[str] = []
    try:
        tasks = load_tasks()
    except ValueError as exc:
        problems.append(str(exc))
        tasks = {}
    for t in tasks.values():
        for d in t["depends_on"]:
            if d not in tasks:
                problems.append(f"{t['id']} depends on unknown {d}")
    # cycle check
    seen: Dict[str, int] = {}

    def visit(n: str, stack: List[str]) -> None:
        if seen.get(n) == 1:
            problems.append("dependency cycle: " + " -> ".join(stack + [n]))
            return
        if seen.get(n) == 2 or n not in tasks:
            return
        seen[n] = 1
        for d in tasks[n]["depends_on"]:
            visit(d, stack + [n])
        seen[n] = 2
    for n in tasks:
        visit(n, [])
    for rel, kind in POINTERS.items():
        p = ROOT / rel
        if not p.exists() or p.read_text(encoding="utf-8") != render_pointer(kind):
            problems.append(f"{rel} out of sync with AGENTS.md (run `python3 tools/agentctl.py sync-pointers`)")
    if git("config", "user.name") and git("config", "user.name") != REQUIRED_AUTHOR:
        warnings.append(f"git user.name is '{git('config', 'user.name')}', project requires '{REQUIRED_AUTHOR}' (git config --local user.name)")
    if git("config", "core.hooksPath") != ".githooks":
        warnings.append("git hooks not enabled (run `make hooks`)")
    for tid, c in read_claims().items():
        if c["stale"]:
            warnings.append(f"stale claim {tid} by {c['agent']} ({c['age_hours']:.1f}h)")
    for w in warnings:
        print(f"warn: {w}")
    for p in problems:
        print(f"FAIL: {p}", file=sys.stderr)
    if problems:
        sys.exit(1)
    print(f"doctor: ok ({len(tasks)} tasks, {len(POINTERS)} pointer files in sync)")


def cmd_check_paths(args: argparse.Namespace) -> None:
    agent = args.agent or os.environ.get("AGENT_NAME", "")
    branch = git("branch", "--show-current")
    m = re.match(r"agent/([^/]+)/(.+)$", branch or "")
    if not agent and m:
        agent = m.group(1)
    files = (git("diff", "--cached", "--name-only") if args.staged else git("diff", "--name-only", "main...HEAD")).splitlines()
    if not files:
        print("check-paths: nothing to check")
        return
    tasks = load_tasks()
    claims = read_claims()
    mine = [tid for tid, c in claims.items() if slug(c["agent"]) == slug(agent)] if agent else []
    if m and m.group(2) in tasks and m.group(2) not in mine:
        mine.append(m.group(2))
    others = {tid: c for tid, c in claims.items() if tid not in mine and not c["stale"]}
    my_paths = [p for tid in mine for p in tasks.get(tid, {}).get("paths", [])]
    shared = ["AGENTS.md", ".agents/handoffs/*", ".agents/LEARNINGS.md", ".agents/tasks/*"]
    bad, foreign = [], []
    for f in files:
        for tid in others:
            if path_owned(f, tasks.get(tid, {}).get("paths", [])):
                foreign.append(f"{f} (owned by {tid}/{others[tid]['agent']})")
        if my_paths and not path_owned(f, my_paths + shared):
            bad.append(f)
    for f in foreign:
        print(f"check-paths: {f}", file=sys.stderr)
    for f in bad:
        print(f"check-paths: {f} is outside your claimed paths", file=sys.stderr)
    if foreign or (bad and args.strict):
        sys.exit(1)
    print(f"check-paths: ok ({len(files)} files{', ' + str(len(bad)) + ' outside claim (warning)' if bad else ''})")


# ---------------------------------------------------------------------------------- CLI
def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(prog="agentctl", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def agent_args(p: argparse.ArgumentParser, provider: bool = True) -> None:
        p.add_argument("task")
        p.add_argument("--agent", required=True, help="stable agent name, e.g. codex-1, claude-a, gemini-cli")
        if provider:
            p.add_argument("--provider", default="", help="LLM/provider, e.g. openai/gpt-5, anthropic/claude")

    p = sub.add_parser("context", help="one-shot situational awareness")
    p.set_defaults(fn=cmd_context)
    p = sub.add_parser("board", help="list tasks")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_board)
    p = sub.add_parser("claims", help="list active claims (local + remote branches)")
    p.set_defaults(fn=cmd_claims)
    for name, fn in (("claim", cmd_claim), ("worktree", cmd_worktree)):
        p = sub.add_parser(name, help="claim a task" if name == "claim" else "claim + create isolated git worktree")
        agent_args(p)
        p.add_argument("--force", action="store_true")
        p.add_argument("--note", default="")
        if name == "worktree":
            p.add_argument("--base", default="main")
        p.set_defaults(fn=fn)
    p = sub.add_parser("heartbeat", help="refresh a claim")
    agent_args(p, provider=False)
    p.set_defaults(fn=cmd_heartbeat)
    p = sub.add_parser("release", help="drop a claim, optionally set task status")
    agent_args(p, provider=False)
    p.add_argument("--status", choices=STATUSES)
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_release)
    p = sub.add_parser("handoff", help="write a handoff report")
    agent_args(p)
    p.add_argument("--summary", required=True)
    for opt in ("checks", "contracts", "risks", "next", "base"):
        p.add_argument(f"--{opt}", default="")
    p.set_defaults(fn=cmd_handoff)
    p = sub.add_parser("learn", help="append an atomic learning")
    p.add_argument("observation")
    p.add_argument("--evidence", required=True)
    p.add_argument("--consequence", required=True)
    p.add_argument("--agent", required=True)
    p.add_argument("--hypothesis", action="store_true")
    p.set_defaults(fn=cmd_learn)
    p = sub.add_parser("new-task", help="create a task card")
    p.add_argument("id")
    p.add_argument("--title", required=True)
    p.add_argument("--paths", nargs="*")
    p.add_argument("--deps", nargs="*")
    p.add_argument("--priority", default="P2")
    p.add_argument("--goal", default="")
    p.set_defaults(fn=cmd_new_task)
    p = sub.add_parser("check-paths", help="verify changed files are inside your claim and not in others'")
    p.add_argument("--agent", default="")
    p.add_argument("--staged", action="store_true")
    p.add_argument("--strict", action="store_true")
    p.set_defaults(fn=cmd_check_paths)
    p = sub.add_parser("sync-pointers", help="regenerate CLAUDE.md, GEMINI.md, Cursor/Copilot/... rules from AGENTS.md")
    p.set_defaults(fn=cmd_sync_pointers)
    p = sub.add_parser("doctor", help="validate board, pointers, identity, hooks")
    p.set_defaults(fn=cmd_doctor)

    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
