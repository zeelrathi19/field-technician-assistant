# Contracts: API, tools, model and persistence

Normative implementation specification. “Must” means a condition the implementation must satisfy before completion, not an already verified capability. `IMPLEMENTATION_PLAN.md` establishes scope; this file is the canonical naming/defaults reference.

## As implemented (29 Sep 2026) — read this first

This section overrides anything below that conflicts with it.

| Topic | Implemented contract | Code |
|---|---|---|
| Model-visible tools | `get_work_order{id}`, `update_status{id,status}`, `add_note{id,text}`, `escalate{id,reason}` + terminal, non-executable `respond{kind: answer\|clarify\|unsupported\|refuse, text ≤1200, citations[{section_id, quote}] ≤6, missing[str] ≤5}`. All properties required, `additionalProperties:false`. | `backend/app/tools.py` |
| Tool choice | OpenAI: `tool_choice="required"`, `parallel_tool_calls=false`, `strict:true` (dropped with `MODEL_COMPAT=generic`). Anthropic: `tool_choice={type:any, disable_parallel_tool_use:true}`. SDK retries disabled (`max_retries=0`). | `backend/app/llm/*` |
| Turn budget | ≤`MAX_MODEL_CALLS_PER_TURN`=3 (one transient retry counted), ≤`MAX_TOOL_CALLS_PER_TURN`=3 (rejected calls count), mutations ≤1 (constant). A mutation, accepted or refused, ends the turn. | `backend/app/agent.py` |
| Intent binding | Mutation target = the single explicit ID in the user's text (payload excluded) or, with none, the focus established in an **earlier** turn. Multiple IDs → clarify. Status must be named in the user's words, or "next/advance" = the legal next status. Negated/how-to phrasing → clarify. One action category per message. Note/reason ≥75% grounded in the user's words. Reads: explicit IDs ∪ focus ∪ own roster. | `backend/app/intent.py` |
| Answers | `AnswerVerifier`: verbatim quote check (whitespace/markdown-insensitive, `...` splits), numbers incl. number words, WO IDs, dates, capitalised statuses must occur in cited sections/tool data/roster (user text is not evidence for facts). Failure → whole cited sections ("exact knowledge-base text") or fixed abstention. kb-1/kb-5 always attach kb-2 as related safety source. | `backend/app/grounding.py` |
| ChatResponse | adds `meta{model_calls, tool_calls, latency_ms, provider, is_llm}`; assistant message carries `sources[{kind, section_id, heading, content_hash, text, quotes, related}]`, `cards[work order view]`, `action`, `missing`, `verified`, `outcome`. | `backend/app/agent.py` |
| Extra endpoints | `GET /api/meta` (technician, provider, model, is_llm, prompt/KB version), `GET /api/work-orders` (own roster, read-only, not via LLM). | `backend/app/api.py` |
| Origin policy | POST with an `Origin` header must match `ALLOWED_ORIGINS` or the request host; requests without `Origin` (CLI tools) are allowed. Cookie `fta_browser`: HttpOnly, SameSite=Strict, path `/api`. | `backend/app/api.py` |
| Config | `MODEL_PROVIDER` ∈ {openai, anthropic, offline} (default offline), `MODEL_BASE_URL`, `MODEL_COMPAT` ∈ {openai, generic}, `MODEL_TEMPERATURE` optional; `MODEL_CONTEXT_TOKENS`/`CONTEXT_INPUT_BUDGET` replaced by `HISTORY_MESSAGES`=8 and `HISTORY_CHAR_BUDGET`=12000. | `backend/app/config.py` |
| Persistence | Tables as below plus `users`; `sessions.pending_json`. Failed turns delete their `processing` reservation so the same request ID can be retried; crash-left `processing` rows become `interrupted` at startup. | `backend/app/db.py`, `agent.py` |

## HTTP boundary

Use one browser origin (`http://localhost:8000` locally). Build React with Vite and serve its static build from FastAPI in a multi-stage Docker image. A single Compose app service and named SQLite volume are enough. Development uses the Vite `/api` proxy. Bind published port to `127.0.0.1`; no wildcard CORS. Do not put provider keys in any `VITE_*` variable.

| Method/path | Input | Result |
|---|---|---|
| `POST /api/sessions` | Empty object | 201 `{session_id, messages: [], state: {active_work_order_id: null}}` |
| `GET /api/sessions/{session_id}` | Session cookie + path ID | 200 persisted display messages and allowed focus; 404 for missing/inaccessible |
| `POST /api/sessions/{session_id}/messages` | `{request_id: UUID, message: string}` | 200 `ChatResponse`; 202 if same request is still running |
| `GET /api/sessions/{session_id}/requests/{request_id}` | Scoped identifiers | 200 stored result, 202 pending, or 404 unavailable |
| `GET /api/health` | None | 200 readiness booleans; no config values, credentials or user data |

Use an opaque server-created browser-session cookie (`HttpOnly`, `SameSite=Strict`; `Secure` outside localhost) that binds conversation access to this browser session and principal. Browser session ID is not authentication. The demo's principal is the seed currentUser; deploying multiple real users requires real authentication first. Scope all conversation queries to both principal and browser session; UUID unpredictability alone is insufficient. Allow only same-origin mutating requests; explicitly verify Origin/Host and CSRF policy. Tests using a non-browser client must supply the intended origin.

`ChatResponse` fields:

```json
{
  "request_id": "opaque UUID",
  "session_id": "opaque UUID",
  "outcome": "answered | acted | refused | clarification | error",
  "messages": [{"id": "opaque UUID", "role": "assistant", "text": "server-rendered text", "sources": []}],
  "state": {"active_work_order_id": "WO-003", "needs_clarification": false},
  "action": {"tool": "update_status", "work_order_id": "WO-003", "code": "OK", "version": 2},
  "retryable": false
}
```

Above enum strings describe alternatives, not literal runtime values. `action` and active ID may be null. A source is `{kind: 'knowledge', section_id, heading, content_hash}` or `{kind: 'work_order', id, version}`. UI receives display-safe content, not internal prompts/provider traces. JSON schema must disallow extra request fields. Missing/oversized message → 422/413; conflicting request ID or simultaneous distinct turn → 409; session unavailable → 404; transient provider outage → 503 with request ID; provider authentication/config error → operator-visible failure without exposing a key. Policy refusal is a completed chat outcome (200), not a server fault.

UI retries use the same request ID and unchanged message. A consciously new user message gets a fresh ID. Disable Send while pending, retain the user's draft on recoverable failure, offer New chat, and label active work-order context. If delivery is uncertain, query the receipt endpoint before retrying. Never optimistically display “completed”. Default plain text with preserved line breaks is enough; no unsanitized HTML/Markdown. Accessibility: labelled input/button, keyboard submit, polite live message announcements, visible focus, error text not conveyed by color alone.

## Tool schemas and registry

All argument models use strict types and `extra='forbid'`. No coercion. Decode JSON before Pydantic validation, reject duplicate JSON keys and nonfinite JSON numeric tokens, enforce envelope/argument byte limits. Trim ID and text at the boundary; canonical status strings only. Tool schema generation must match the real validator; adapter translation must reject unsupported schema features rather than silently weakening validation.

```json
{
  "name": "update_status",
  "parameters": {
    "type": "object",
    "properties": {
      "id": {"type": "string", "pattern": "^WO-[0-9]{3}$"},
      "status": {"type": "string", "enum": ["Open", "In Progress", "On Hold", "Completed"]}
    },
    "required": ["id", "status"],
    "additionalProperties": false
  }
}
```

The other tools share the ID schema: `get_work_order` requires only `id`; `add_note` requires `id,text` with trimmed text length 1–2000; `escalate` requires `id,reason` with trimmed reason length 1–500. Enforce bounds locally even if provider JSON-schema support differs. The registry is a fixed mapping to callable handlers; tools are never loaded from a user path or dynamic import. No model argument can set actor, author, role, version, DB path, timestamp, request ID, or policy.

`ToolResult = {ok: bool, code: str, message: str, data: object|null}`. Result messages are backend templates. Public error codes: `UNKNOWN_TOOL`, `INVALID_ARGUMENTS`, `ACCESS_DENIED_OR_NOT_FOUND`, `INVALID_TRANSITION`, `INTENT_MISMATCH`, `CLARIFICATION_REQUIRED`, `MULTIPLE_ACTIONS`, `CONFLICT`, `LIMIT_REACHED`, `PROVIDER_UNAVAILABLE`, `INTERNAL_ERROR`. Internal logs may distinguish denial/not-found; public text must not reveal another technician's name/details.

Read data permits only ID, title, asset type, status, due date, recorded steps, version, and owned note/escalation information within result bounds. Do not return the whole fixture or other users' records. Mutation data includes persisted operation ID, order ID/version, changed status or note/escalation ID, and server timestamp. Notes and reasons remain untrusted text on subsequent turns.

## Intent/target binding before execution

The LLM must still choose the actual tool call. A small deterministic `IntentGuard` constrains whether that proposal represents an explicitly permitted current-turn action; it is not a replacement tool router or a second LLM.

Use anchored, case-insensitive supported commands (optional polite `please` and final punctuation), not substring detection. For status changes support `start <target>`, `put <target> on hold`, `mark <target> complete/completed/done`, and `set <target> to <canonical status>`. Target is exactly a fixture-format ID or `it`/`this work order`. `Open` remains a valid schema enum but no transition targets it. Reject negated, hypothetical, quoted, conflicting, compound, or unsupported action phrasing with a clarification and an example supported command. Do not interpret “don't complete it” or “how do I mark it complete?” as permission. This small initial grammar trades language flexibility for testable action control; document it in the UI help.

For notes: `add note to <target>: <verbatim text>` (allow optional article `a` after `add`); for escalation: `escalate <target>: <verbatim reason>`. Also support `escalate <target> because <verbatim reason>`. Preserve payload apart from outer whitespace; compare proposed payload with the extracted current-user payload. The model cannot summarize, add instructions, or substitute text. A note's contents never authorize another action, even if they resemble a command. Missing payload asks the user to repeat the complete command; do not infer an old reason from history.

Read-only questions need not use this grammar. Server extracts explicit ID references from the current question and stores candidate IDs; every model read target must be in that set or match the unique valid session focus. If several IDs are referenced, reads may address the explicit IDs, but mutation focus remains ambiguous. If a requested comparison cannot fit the bounded two-call turn, ask to narrow the request rather than increase the loop.

Use `IntentBinding(action, target_id, exact_payload_or_status, source_message_id)` as server-owned state. Tool call mismatch → `INTENT_MISMATCH`, no write. An accepted pronoun binding requires session focus valid at the time of the turn; an explicit ID always overrides old focus. Failures never silently revert to a previously focused ID. Clarification is a new user turn and must establish a fresh binding; a bare “yes” does not authorize a fabricated status or payload.

## Model wrapper and structured answers

Define neutral DTOs: `ModelMessage(role, content, tool_calls?, tool_call_id?)`, `ToolSpec`, `ToolCall(call_id, name, arguments_json)`, `ModelUsage(input_tokens?, output_tokens?)`, `ModelDecision(tool_calls, evidence_selection?, finish_reason, usage)`. Provider-specific continuation items stay in an opaque adapter-owned continuation object, not domain memory. Never log or request private reasoning. Accept either a tool-call decision or evidence selection; reject contradictory mixed output and model text that does not validate.

`ModelClient.generate(messages, tools, response_schema, limits) -> ModelDecision` is the boundary. Adapter capabilities declare native tools, strict structured output, parallel call controls, tokenizer/context capacity and whether response schema can coexist with tools. The initial adapter uses a supported official SDK. A provider lacking required features fails startup rather than falling back to parsing executable JSON from prose. A fake adapter yields deterministic proposals for tests only.

If a provider cannot combine a final structured response with tool definitions, use an adapter-supported equivalent structured output mode or return a capability error; do not add a fifth executable business tool silently. Contract tests must exercise both a KB-only response and each native business tool. Provider portability means preserving this contract through an adapter, not pretending every provider accepts identical wire JSON.

`EvidenceSelection = {coverage: supported|partial|unsupported|clarify, section_ids: list[str], missing_question_spans: list[str]}`. For supported coverage require nonempty valid IDs and no missing spans. Partial requires both valid IDs and literal missing spans. Unsupported requires no IDs and renders the fixed abstention (optionally independently attach relevant approved safety source). Clarify uses a fixed narrower-question prompt. Deduplicate IDs in source order and include all prerequisite warnings. Unknown IDs, inconsistent fields, excess size, refusal, truncation, or invalid output → safe error/abstention, never unvalidated prose.

Native calling sequence: create request with four tool definitions and `parallel_tool_calls=false` when supported; inspect structured calls; validate; execute one; correlate any follow-up tool result using the provider call ID. Preserve provider-required continuation items inside the adapter when doing the optional second model request. Record the tool result even when replying deterministically without another model request. Do not claim the model executed Python itself.

## Persistence and transactions

Use SQLite foreign keys, WAL on local disk, bounded busy timeout, parameterized SQL, UTC timestamps, and schema version 1. No network/shared filesystem database. Fields below are an implementation blueprint, not a mandatory ORM.

| Table | Key / minimum columns |
|---|---|
| `work_orders` | `id` PK, fixture fields, `version` integer, `escalated` boolean |
| `notes` | `id` PK, order FK, actor ID, text, created_at |
| `escalations` | `id` PK, order FK, actor ID, reason, created_at |
| `sessions` | `id` PK, user ID, browser-session binding, focus ID nullable, candidate IDs JSON, clarification JSON nullable, updated_at |
| `messages` | `id` PK, session FK, turn/request ID, sequence, role, display content, source refs |
| `requests` | composite `(user_id,session_id,request_id)` unique; input hash, processing/completed/error state, response JSON, timestamps |
| `audit_events` | operation ID PK, request FK, actor, tool, order ID, old/new version/status, code, timestamp; no payload bodies |
| `schema_meta` | schema version and fixture hash |

Validate the seed once: unique IDs, exact status enums, currentUser present, assignment references nonempty. Seed only an empty initialized DB; unknown schema/changed seed with existing data must fail or require explicit migration/reset. Never merge seed data over user changes on restart.

1. Atomically reserve request key and input hash; exact completed duplicate replays, different hash conflicts, pending duplicate returns 202.
2. Serialize turns per session; a different concurrent message returns 409. Use one worker's per-session lock with cleanup for assessment; DB uniqueness remains the durable duplicate protection.
3. Build context and call model outside write transactions. Capture observed order versions only as preconditions, not truth.
4. For execution `BEGIN IMMEDIATE`; reload record, authorize, check intent/status/current version, then persist mutation, audit, focus/messages and complete response in **the same transaction**. Missing expected version for an explicitly bound first-turn mutation is obtained during this transaction; do not force an unnecessary model read.
5. Roll back all writes on failure. Policy refusal can persist its own request result/audit without changing the order. On committed result plus network loss, retry replays it.
6. On process restart, any `processing` request with no committed outcome is marked interrupted, never auto-executed. Return an explicit retryable error and let a new user request start again. Atomic mutation/result commits ensure there is no committed mutation without its durable receipt.

Two different sessions requesting a concurrent status change cannot both succeed on the same initial version. With new notes, distinct request IDs may legitimately append twice; only retry identity defines duplication. Preserve all earlier notes. Escalations append events and set a flag; they never email, resolve, or alter status implicitly.

## Configuration defaults (single source of truth)

| Setting | Initial value / validation |
|---|---|
| `MODEL_PROVIDER` | `openai` initially; allowlisted registered adapter |
| `MODEL_NAME` | Required explicit supported model; no invented/latest alias assumption |
| `MODEL_API_KEY` | Required server secret; mapped inside adapter |
| `MODEL_TIMEOUT_SECONDS` | 30, positive; one transient retry only within remaining turn deadline |
| `TURN_TIMEOUT_SECONDS` | 60; no provider request beyond remaining budget |
| `MAX_MODEL_CALLS_PER_TURN` | 2 total attempts, including retry |
| `MAX_TOOL_CALLS_PER_TURN` | 2; attempted calls count, including rejection |
| `MAX_MUTATIONS_PER_TURN` | Hard invariant 1; not user-configurable upward |
| `MODEL_CONTEXT_TOKENS` | Required verified provider capacity; never guess from model name |
| `CONTEXT_INPUT_BUDGET` | 6000 tokens maximum, further reduced by actual capacity |
| `MAX_OUTPUT_TOKENS` | 1024 initially; reserve provider reasoning allowance if model requires it |
| `MODEL_CONCURRENCY` | 4 for the one-worker demo; bounded queue/reject overload |
| `MAX_MESSAGE_CHARS` | 8000 |
| `MAX_NOTE_CHARS` / `MAX_REASON_CHARS` | 2000 / 500 |
| `DATABASE_PATH` | `/data/assistant.sqlite3` in container |
| `KNOWLEDGE_PATH` / `WORK_ORDERS_PATH` | `/app/inputs/knowledge.md`, `/app/inputs/work_orders.json` |
| `LOG_LEVEL` | INFO; no default content logging |

The hard policy must not be configurable off. Invalid limits fail startup. Timeouts/queue limits/token estimates are engineering defaults to evaluate, not claims of measured capacity. Provider retry is permitted only before a write and consumes the same budgets; SDK hidden retries must be disabled or included in these counters.
