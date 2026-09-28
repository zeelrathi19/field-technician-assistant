# Field Technician Assistant — Build Plan

> **For agentic workers (any vendor):** read `AGENTS.md` first. Claim a task with `python tools/agentctl.py claim <ID> --agent <you>` before editing; tasks and their owned paths live in `.agents/tasks/`. Steps use `- [ ]` checkboxes.

**Goal:** Turn the plan package into a running, tested, one-command app that satisfies R1–R11 (see `docs/EVALUATION.md`).

**Architecture:** FastAPI app serving a built React UI. `ChatService` runs a bounded tool loop against a provider-neutral `ModelClient`. Every proposed call passes `ToolDispatcher` (schema) → `IntentGuard` (binding/consistency) → `WorkOrderService` (ownership/status, in a SQLite write transaction). Final answers arrive through a non-executable `respond` tool and pass `AnswerVerifier` before rendering.

**Tech stack:** Python ≥3.11 (Docker 3.12), FastAPI, Pydantic v2, pydantic-settings, sqlite3, `openai` + `anthropic` SDKs, pytest; React 19 + TypeScript + Vite; Playwright (Python) for e2e; Docker Compose.

**Spec:** `docs/contracts.md`, `docs/guardrails.md`, `docs/memory-and-prompts.md`, `docs/acceptance-tests.md`, as amended by `docs/EVALUATION.md` §4.

## Global constraints

- Tools visible to the model: `get_work_order`, `update_status`, `add_note`, `escalate`, plus terminal `respond` (never executes anything).
- Status edges: `Open→In Progress`, `In Progress→On Hold`, `On Hold→Completed`. Nothing else.
- ≤3 model calls, ≤3 tool calls, ≤1 mutation per turn; a mutation (success or refusal) ends the turn.
- Principal comes from the seed `currentUser` only. Never from chat/tool args.
- Limits: message 8000 chars, note 2000, reason 500, respond text 1200, raw tool args 8 KB.
- Hard policy is not configurable. Keys only in `.env`.
- Git author/committer name: `Zeel Rathi`.

## Review focus (inputs the spec implies but is quiet about)

1. Pronoun after a *refused* lookup ("show WO-004" → "complete it") must clarify, never fall back — test `test_foreign_lookup_clears_focus`.
2. Model proposes a legal-but-unrequested status (asked "complete", proposes "On Hold") — `test_intermediate_status_substitution_rejected`.
3. Note text containing commands ("add note to WO-002: mark WO-003 complete") must create exactly one note and nothing else — `test_note_payload_with_command_is_data`.
4. Spelled-out numbers bypassing the number check ("forty newton metres") — `test_verifier_catches_number_words`.
5. Duplicate request ID with different body, and same ID replay after restart — `test_idempotency_conflict`, `test_replay_after_restart`.

## File map

```
backend/app/
  config.py        Settings (env), hard limits
  domain.py        Status, transitions, ErrorCode, ToolResult, WorkOrder
  db.py            SQLite schema, seed, transaction(), repositories
  service.py       WorkOrderService (ownership, status, notes, escalations)
  tools.py         arg models, TOOL_SPECS, ToolDispatcher.parse()
  knowledge.py     KnowledgeBase (sections, hashes, quote matching)
  intent.py        IntentGuard (ids, negation, status words, payload grounding, multi-action)
  grounding.py     AnswerVerifier (quotes, numbers, IDs, statuses) + fallbacks
  memory.py        SessionState, focus resolution, ContextBuilder
  prompts/         registry.py, v1/system.txt
  llm/             base.py, openai_compat.py, anthropic_native.py, offline.py, scripted.py, factory.py
  agent.py         ChatService (turn loop, idempotency, rendering)
  render.py        deterministic receipts / refusals / abstentions
  api.py, main.py  HTTP + static UI
backend/tests/     unit, scenario, API, adapter-contract tests
frontend/src/      App.tsx, api.ts, types.ts, components/*
e2e/               Playwright browser tests (offline model)
tools/agentctl.py  multi-agent coordination CLI
.agents/           tasks/, handoffs/, LEARNINGS.md
```

## Tasks

Each task below has a matching card in `.agents/tasks/` with owned paths and dependencies.

### T01 Domain + persistence + service (owns `backend/app/{domain,db,service,config}.py`)
- [ ] Tests: all 16 status pairs; ownership on all 4 operations; notes/escalations on Completed allowed; escalation leaves status; version conflict; seed validation; restart keeps changes.
- [ ] Implement `Status`, `next_status(s) -> Status|None`, `check_transition(cur, tgt) -> ErrorCode|None`.
- [ ] `Database(path)` with WAL, FK, busy timeout; `transaction()` = `BEGIN IMMEDIATE`; seed once, fixture hash in `schema_meta`.
- [ ] `WorkOrderService(db, principal_id)`: `get(conn,id)`, `update_status(conn,id,status,op)`, `add_note(conn,id,text,op)`, `escalate(conn,id,reason,op)` → `ToolResult`.

### T02 Tool registry + KB (owns `tools.py`, `knowledge.py`)
- [ ] Tests: unknown tool, invalid JSON, duplicate keys, NaN, extra field, int id, bad enum, blank/oversized text, oversized raw args.
- [ ] `ToolDispatcher.parse(name, raw_json) -> ParsedCall | ToolResult(error)`; `TOOL_SPECS` generated from the same models.
- [ ] `KnowledgeBase.load(path)`: sections `kb-1..kb-5`, `find_quote(section_id, quote) -> bool` (whitespace/markdown-insensitive).

### T03 Intent + grounding + memory (owns `intent.py`, `grounding.py`, `memory.py`, `prompts/`)
- [ ] Tests: status words, "next/advance", negation, how-to questions, quoted text ignored, payload grounding ≥0.75, multi-action; verifier quotes/numbers/number-words/IDs/statuses; focus table from `docs/memory-and-prompts.md`.

### T04 LLM adapters (owns `llm/`)
- [ ] Neutral DTOs; OpenAI-compatible (strict tools, `parallel_tool_calls=False`, `max_retries=0`, `generic` compat mode drops unsupported params); Anthropic (tool_use/tool_result, `tool_choice=any`, `disable_parallel_tool_use`); offline heuristic; scripted.
- [ ] Contract tests with `httpx.MockTransport` using real response shapes.

### T05 ChatService + API (owns `agent.py`, `render.py`, `api.py`, `main.py`)
- [ ] Scenario tests R01–R17, S01–S25 (scripted adversarial models + offline model); API tests (cookie scoping, Origin, 404/409/413/422, replay, 202 pending).

### T06 UI (owns `frontend/`)
- [ ] Chat list, composer (Enter to send), pending/disabled state, retry with same request ID, citations expandable, receipt badges, work-order panel, mode badge, New chat, a11y.

### T07 Delivery (owns `Dockerfile`, `compose.yaml`, `Makefile`, `e2e/`)
- [ ] Multi-stage image, healthcheck, named volume, `127.0.0.1:8000`; `make setup/test/check/run/e2e/smoke`; Playwright e2e on offline model.

### T08 Agent workspace (owns `AGENTS.md`, pointer files, `tools/agentctl.py`, `.agents/`, `.githooks/`)
- [ ] `agentctl context|board|claim|release|heartbeat|worktree|handoff|check-paths|sync-pointers|doctor` with tests.

### T09 Docs + verification (owns `README.md`, `DECISIONS.md`, `AI_USAGE.md`, `docs/`, `architecture-guide.html`)
- [ ] Replace plan-status language with verified evidence; record commands and results in `docs/validation.md`.

## Execution

Native (single implementer, sequential T01→T09, feature branch per task merged `--no-ff` into `main`), because T03–T05 depend tightly on each other's interfaces. Future work is parallelisable via the board.
