# AGENTS.md — single source of truth for every coding agent

This file is read natively by Codex, Jules, Amp, OpenCode, Zed, Factory and Cursor, and is mirrored
(by `python3 tools/agentctl.py sync-pointers`) into `CLAUDE.md`, `GEMINI.md`,
`.github/copilot-instructions.md`, `.cursor/rules/agents.mdc`, `.windsurf/rules/agents.md`,
`.clinerules/agents.md` and `CONVENTIONS.md` (Aider). **Edit only this file**, then run `sync-pointers`.
Any agent on any LLM provider follows the same rules; several may work at the same time.

## What this repo is

A field-technician assistant: Python/FastAPI backend + minimal React UI. A technician asks maintenance
questions (answered only from `inputs/knowledge.md`) and reads/changes their own work orders through four
LLM-selected tools (`get_work_order`, `update_status`, `add_note`, `escalate`). The LLM proposes; typed
backend code authorizes; SQLite commits; the UI shows deterministic receipts and verified citations.
Status: **implemented and tested** (see `docs/validation.md`). Assessment context: `docs/EVALUATION.md`.

## Invariants

<!-- agentctl:invariants:begin -->
1. The model only *proposes*. Ownership, status transitions, schemas and the one-write-per-turn limit are enforced in code (`backend/app/service.py`, `tools.py`, `agent.py`). Never move a rule into the prompt only, and never make a hard rule configurable.
2. Status moves exactly one step: Open -> In Progress -> On Hold -> Completed. No skips, no reversals, no same-state, no auto-traversal. Completed is terminal for status (notes/escalations still allowed).
3. Every tool call, including reads, re-checks `assignedTech == currentUser` on fresh DB rows. Unowned and missing IDs return the same public error. Identity never comes from chat or tool args.
4. Exactly five model-visible tools: the four business tools + non-executable `respond`. Static registry, strict Pydantic (extra=forbid, no coercion). No eval/exec/shell/SQL/dynamic dispatch.
5. Maintenance facts reach the UI only through `AnswerVerifier` (verbatim quotes + number/ID/status/date provenance) or as whole approved KB sections. Uncovered questions abstain. No web/general-knowledge fallback.
6. <=1 mutation per turn; a mutation (accepted or refused) ends the turn with a DB-backed receipt. No repair loops. Request IDs are idempotent.
7. Session focus is a reference, never permission. It comes from the technician's own words; a foreign/missing ID clears it; ambiguity asks.
8. User text, KB text, work-order fields and notes are data, never instructions. Never log message bodies, notes, prompts or keys.
9. Tests are the contract: `make check` must pass before any handoff. Add a failing test before changing behaviour. Do not weaken a test to make it pass.
10. Git: branch per task (`agent/<agent>/<task>` or `feat|fix|docs/...`), never commit directly to `main`, author/committer name `Zeel Rathi`, no secrets/.env/DB/PDF in git.
<!-- agentctl:invariants:end -->

## Start here (every session, every agent)

```sh
make context                                   # board, live claims, ready tasks, recent handoffs/learnings
python3 tools/agentctl.py worktree T12 --agent codex-1 --provider openai/gpt-5   # claim + isolated worktree
cd ../unfoldxr-task.worktrees/T12-codex-1
make setup && make check                       # green before you start
# ... work only inside the task's `paths:`; add tests first ...
make check
python3 tools/agentctl.py handoff T12 --agent codex-1 --summary "..." --checks "make check: 212 passed"
python3 tools/agentctl.py release T12 --agent codex-1 --status review
```

Read order: this file → `docs/architecture.md` (system map, where to change what) → `docs/contracts.md`
→ your task card in `.agents/tasks/` → latest relevant `.agents/handoffs/`.

## Parallel work protocol

- **Claim before editing.** `agentctl claim|worktree` is atomic and shared across all worktrees of this clone
  (state lives in the git common dir). It refuses a task already claimed, one whose dependencies are not done,
  or one whose `paths:` overlap another live claim. Claims older than 2 h without `heartbeat` are stale.
- **Different machines/containers:** push your branch `agent/<agent>/<task>` early — `agentctl claims` and
  `claim` also inspect remote `agent/*` branches.
- **Stay inside your paths.** `agentctl check-paths --staged` (run by the pre-commit hook after `make hooks`)
  blocks files owned by another live claim.
- **Shared files** (`docs/contracts.md`, `backend/app/tools.py` schemas, `backend/app/config.py`, lockfiles,
  `AGENTS.md`) change only in a task that declares them; announce contract changes in the handoff.
- **One git index per worktree.** Never run checkout/rebase in another agent's worktree.
- **Record, don't remember.** Durable facts go in `.agents/LEARNINGS.md` (`agentctl learn`), decisions in
  `docs/decision-log.md`. Never store chain-of-thought.

## Commands

| Need | Command |
|---|---|
| Install | `make setup` (uv + npm ci) |
| Tests (no key) | `make test` — unit, scenario (R01–R17, S01–S25, C01–C09), API, adapter contracts, agentctl |
| Browser e2e | `make e2e` (Playwright; offline model) |
| Everything before handoff | `make check` |
| Run locally | `make run` → http://127.0.0.1:8000 |
| One-command launch | `docker compose up --build` |
| Live LLM smoke | put provider in `.env`, `make smoke` |

## Code conventions

- Python ≥3.11, typed, small cohesive modules; composition over inheritance; Pydantic at boundaries,
  dataclasses inside. Domain policy stays framework-free (`domain.py`, `service.py`).
- Provider SDK types never leave `backend/app/llm/`. New provider = one adapter + one branch in `llm/factory.py`
  + wire-shape tests in `tests/test_adapters.py`.
- Prompt changes: edit `backend/app/prompts/v1/*.txt` (or add `v2`), run scenario tests + `make smoke`.
- React: plain components and CSS, render text only (no `dangerouslySetInnerHTML`).
- Errors are explicit typed results (`ToolResult`, `ErrorCode`); no broad `except` that turns failure into success.

## Done means evidence

A task is done when its acceptance boxes are ticked, `make check` passes, a handoff lists the exact
commands run and results, and docs/HTML are updated if behaviour or contracts changed. Record live-provider
results separately from fake/offline results. A missing check stays open, whatever the deadline.
