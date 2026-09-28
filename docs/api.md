# API, tools and data contracts

The HTTP API is same-origin JSON under `/api`. Interactive OpenAPI: `/api/docs`. Configuration variables are listed in [setup.md](setup.md#configuration-reference).

## Sessions and security

- **Session cookie.** `POST /api/sessions` sets `fta_browser` (HttpOnly, SameSite=Strict, path `/api`, 30 days). Every session, message and receipt is scoped to that cookie *and* the technician, so another browser gets `404`.
- **Origin.** POSTs that carry an `Origin` header must match `ALLOWED_ORIGINS` or the request host. Requests without `Origin` (CLI tools) are allowed.
- **Size.** Bodies over 64 KB get `413` before parsing. A message over `MAX_MESSAGE_CHARS` also gets `413`.

## Endpoints

| Method and path | Request | Success | Errors |
|---|---|---|---|
| `GET /api/health` | — | `{ok, database, knowledge_sections, provider}` | — |
| `GET /api/meta` | — | `{technician{id,name}, provider, model, is_llm, prompt_version, kb_hash, limits{max_message_chars}}` | — |
| `GET /api/work-orders` | — | `{work_orders: RosterItem[]}`: your orders only | — |
| `POST /api/sessions` | `{}` | `201 {session_id, messages: [], state}` | 403 origin |
| `GET /api/sessions/{id}` | — | `{session_id, messages[], state}` | 404 |
| `POST /api/sessions/{id}/messages` | `{request_id: uuid, message: string}` (extra fields rejected) | `200 ChatResponse` · `202 {status:"pending"}` while the same request runs | 404 · 409 (other message running / request_id reused with different text) · 413 · 422 · 503 provider · 500 |
| `GET /api/sessions/{id}/requests/{request_id}` | — | Stored `ChatResponse` · `202` pending | 404 |

The UI reuses the same `request_id` for a retry, so a network failure can never apply a change twice. Policy refusals are normal `200` responses with `outcome: "refused"`.

## ChatResponse

```jsonc
{
  "request_id": "uuid", "session_id": "uuid",
  "outcome": "answered | acted | refused | clarification | error",
  "messages": [
    {"id": "…", "role": "user", "text": "Mark it complete"},
    {"id": "…", "role": "assistant", "text": "WO-003 status changed from On Hold to Completed.",
     "outcome": "acted", "verified": true, "missing": [],
     "sources": [ /* KnowledgeSource */ ], "cards": [ /* WorkOrderCard */ ], "action": { /* Receipt */ }}
  ],
  "state": {"active_work_order_id": "WO-003", "candidates": [], "needs_clarification": false},
  "action": { /* Receipt or null */ },
  "retryable": false,
  "meta": {"model_calls": 1, "tool_calls": 1, "latency_ms": 840, "provider": "openai", "is_llm": true}
}
```

| Type | Fields |
|---|---|
| KnowledgeSource | `kind:"knowledge"`, `section_id` (`kb-1`…`kb-5`), `heading`, `content_hash`, `text` (the full approved section), `quotes[]` (verified), `related` (true = attached lockout section) |
| WorkOrderCard | `id, title, assetType, status, dueDate, steps[], version, escalated, allowedNextStatus, notes[≤5]{id,text,createdAt}, notesTruncated, escalations[≤3]` (never the assignee) |
| Receipt | `tool, work_order_id, code, ok`, and when relevant `status, previousStatus, allowedNextStatus, text, reason, version, at` |
| RosterItem | `id, title, assetType, status, dueDate, version, escalated, noteCount, allowedNextStatus` |
| Error body | `{request_id, session_id, outcome:"error", code, message, retryable}` |

Error codes: `UNKNOWN_TOOL`, `INVALID_ARGUMENTS`, `ACCESS_DENIED_OR_NOT_FOUND`, `INVALID_TRANSITION`, `INTENT_MISMATCH`, `CLARIFICATION_REQUIRED`, `MULTIPLE_ACTIONS`, `CONFLICT`, `LIMIT_REACHED`, `PROVIDER_UNAVAILABLE`, `INTERNAL_ERROR`.

## Model-visible tools

All object schemas set `additionalProperties: false` and list every property as required. Validation uses strict Pydantic (no coercion, strings trimmed); the JSON Schemas are written to match it exactly.

| Tool | Arguments | Effect |
|---|---|---|
| `get_work_order` | `id` (`^WO-[0-9]{3}$`) | Read one owned order |
| `update_status` | `id`, `status` ∈ `Open`, `In Progress`, `On Hold`, `Completed` | One legal step |
| `add_note` | `id`, `text` (1–`MAX_NOTE_CHARS`) | Append a note (actor and time set by the server) |
| `escalate` | `id`, `reason` (1–`MAX_REASON_CHARS`) | Set the escalation flag and record the reason; status unchanged |
| `respond` | `kind` ∈ `answer`, `clarify`, `unsupported`, `refuse`; `text` (≤1200); `citations[≤6]{section_id, quote}`; `missing[≤5]` | Ends the turn; checked by AnswerVerifier; **never executes anything** |

Raw arguments are limited to 8 KB. Duplicate JSON keys and NaN/Infinity are rejected.

## Persistence (SQLite, schema v1)

| Table | Purpose |
|---|---|
| `schema_meta` | Schema version, and the seed hash (a changed fixture refuses to start) |
| `users` | The seed `currentUser` |
| `work_orders` | Fixture fields, plus `version` and `escalated` |
| `notes`, `escalations` | Append-only, with actor, timestamp and `request_id` |
| `sessions` | `user_id`, `browser_id`, `focus_id`, `candidates_json`, `pending_json` |
| `messages` | Display text and payload (sources/cards/receipt) in sequence |
| `requests` | `(user, session, request_id)` → input hash, state (`processing`, `completed`, `interrupted`), response |
| `audit_events` | Tool, order, old/new status and version, result code (no payload text) |

Writes use `BEGIN IMMEDIATE` (the write lock is taken before the rows being checked are read), WAL, foreign keys and a 5 s busy timeout.
