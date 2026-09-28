# Development

Several humans and AI agents (any tool, any model) can work on this repo at the same time. The short rules are in [AGENTS.md](../AGENTS.md). This page is the full workflow.

## Setup

```sh
make setup && make hooks   # deps + git hooks (secret scan, claim check, author check, no commits on main)
make check                 # must be green before you start
```

Git identity for this repo (set locally, never globally): `Zeel Rathi <zeelrathi807@gmail.com>`.

## The task board

Task cards live in `.agents/tasks/T*.md`:

```yaml
---
id: T12
title: Postgres repository for multi-instance deployment
status: todo            # todo | in_progress | review | done | blocked
priority: P3
owner:
depends_on: [T05]
paths: [backend/app/db.py, backend/app/service.py, compose.yaml]   # the files this task may change
---
```

| Command (`python3 tools/agentctl.py …`) | Does |
|---|---|
| `context` (or `make context`) | Invariants, board, live claims, ready tasks, recent handoffs and learnings |
| `board` / `claims` | List tasks / list active claims (local and remote `agent/*` branches) |
| `new-task T21 --title … --paths … --deps …` | Create a card |
| `worktree T21 --agent NAME --provider LLM` | Claim, then create `../<repo>.worktrees/T21-NAME` on branch `agent/NAME/T21` |
| `claim` / `heartbeat` / `release --status review` | Manage a claim; `release` updates the card |
| `check-paths --staged` | Block files owned by someone else's live claim (runs in the pre-commit hook) |
| `handoff T21 --agent NAME --summary … --checks … --risks … --next …` | Write `.agents/handoffs/<date>-T21-NAME.md` |
| `learn "observation" --evidence … --consequence … --agent NAME` | Append to `.agents/LEARNINGS.md` |
| `adapters list/add/remove gemini\|aider\|cline` | Tiny per-tool config for tools that don't read AGENTS.md natively |
| `doctor` | Validate the board, dependency cycles, the CLAUDE.md import, git identity and hooks |

Claims live in the git *common* directory, so every worktree of a clone sees them instantly, and they are created atomically. On separate machines, push your `agent/<name>/<task>` branch early so others see it.

### Running several agents at once

1. Give each agent its own task and its own worktree: `agentctl worktree <T> --agent <name>`. Don't point several agents at one directory. They fight over the git index and each other's files.
2. Tasks whose `paths:` overlap can't be claimed together. Split the work so paths don't overlap.
3. Each agent finishes with `make check`, then a handoff, then `release --status review`.
4. One integrator merges the branches with `--no-ff` after reading the diff and re-running `make check` / `make e2e`.

## Git workflow

- Branch per task: `agent/<agent>/<task>`, or `feat/…`, `fix/…`, `docs/…`. The hook blocks commits on `main` (`ALLOW_MAIN_COMMIT=1` is for merges only).
- Merge with `--no-ff` so every change stays visible as a unit. Push `main` only after `make check` passes.
- Never commit `.env`, databases, the assignment PDF or tokens. `tools/scan_secrets.py` runs on every commit and in `make check`.

## Common changes

| Change | Where | Also |
|---|---|---|
| Status rule / ownership | `domain.py`, `service.py` | 16-pair and ownership tests |
| What counts as "asked for" | `intent.py` | `test_intent.py` plus a scenario with a hostile `ScriptedModel` |
| What counts as grounded | `grounding.py` | `test_grounding.py`, `test_review_policy.py` |
| Prompt | `prompts/v1/system.txt` (or add `v2` in `prompts/registry.py`) | Scenarios + `make smoke` on at least one real provider |
| New provider | `llm/<name>.py` implementing `generate(system, messages, tools, *, max_output_tokens, timeout) -> ModelDecision`; branch in `llm/factory.py`; literal in `config.py` | Contract tests with recorded request/response shapes; a row in docs/setup.md |
| New tool | Pydantic model + schema in `tools.py`, service method, handling in `agent.py` | Update invariant 4, docs/api.md and adversarial scenarios. This is a contract change, so get it reviewed. |
| UI | `frontend/src/**` | `make e2e` (includes axe) |

## Documentation rules

- Keep docs current. When behaviour or a contract changes, update `docs/` in the same branch.
- Record decisions in `docs/decision-log.md` (ID, choice, why, alternative, evidence).
- Record evidence in `docs/validation.md`: commands actually run, with results.
- `docs/archive/` is the historical pre-build plan. Don't update it.
