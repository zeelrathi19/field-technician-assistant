# Guardrails

Every rule below is enforced in code, *after* the model and *before* the database or the UI. The prompt repeats the rules only to reduce bad proposals. Tests named in the last column prove each rule against an adversarial model (`ScriptedModel`), not a cooperative one.

## Hard rules

| Rule | Enforced in | Behaviour | Tests |
|---|---|---|---|
| Only your own work orders, reads included | `service.py` on every call, on fresh rows | "Work order X is not available to you". Identical for foreign and missing IDs, and no details are shown. | `test_service.py`, R09, R10, S01, S25 |
| Exact status chain | `domain.TRANSITIONS`, checked inside `BEGIN IMMEDIATE` | Only Open→In Progress→On Hold→Completed. Skips, reversals and same-state requests are refused with the allowed next status. Completed is terminal. | 16-pair test, R04–R08, C08 |
| Known tools, strict arguments | `tools.ToolDispatcher` | Unknown names; invalid, duplicate-key or NaN JSON; extra fields; wrong types; bad enums; blank or oversized text are all rejected before any service call | `test_tools.py`, R11, R12, S21 |
| One write per turn, no repair | `agent.py` | More than one write proposed → the whole batch is refused. After any write, accepted or refused, the turn ends with a receipt. | S07, S23 |
| Identity from the server | `db.principal()` | Chat and tool arguments can't set actor, role or ID | R09 |
| Idempotent requests | `requests` table | A retry replays the stored response; the same ID with different text returns 409 | S16, S17, S19 |
| Atomic receipts | one transaction | Write + audit + messages + stored response commit together | `test_rollback_on_failure`, C06 |

## Proposal checks (IntentGuard)

The LLM picks the call from natural language. Before any write, code checks that the proposal matches what the technician asked:

| Check | Example refused |
|---|---|
| Target is the single ID in the message, or the focus from an earlier turn | "Mark WO-003 complete" → model proposes WO-010 |
| Several IDs → ask which | "Show WO-001 and WO-003. Mark it complete." |
| The requested status is named ("done/close" → Completed, "hold/pause" → On Hold, "start" → In Progress), or "next/advance" equals the one legal next status | "Mark WO-001 complete" → model proposes On Hold (a workaround) |
| Not negated or hypothetical, for *this* action | "Don't complete WO-003", "How do I mark it complete?" (but "Complete WO-003, never mind the note" is fine) |
| One kind of change per message | "Add a note to WO-002 and escalate it" |
| Note text or reason taken from the technician (≥75% of the content words appear in their message) | "Escalate WO-006" → model invents "safety hazard" |

These are deliberately conservative heuristics: when unsure they ask, they never pick a different action. The hard rules above don't depend on them.

## Answer checks (AnswerVerifier)

Every turn that doesn't write ends with the model's `respond{kind, text, citations, missing}`. Before anything is shown:

- **Citations:** each quote must appear verbatim in its cited section (whitespace and markdown ignored).
- **Facts in the text:** every number (including words like "ninety"), date, WO-ID, asset code (e.g. CU-4400) and status name must appear in the evidence: the cited sections, this turn's tool results, or the technician's own order list. The user's own words are not evidence.
- **Status claims:** a claim about an order ("WO-003 is done") must match *that order's* current status.
- **No claimed actions:** text like "I've marked…" or "note added" is rejected, because a `respond` turn never writes.
- **No markup:** no HTML or markdown links/images.
- **Work-order counts:** "N work orders" must equal a count the server derives from the technician's own list (total or per status). The count licenses no other number in the text.
- **Refusals are server text:** for `kind=refuse` the model's wording is discarded. An unowned or unknown ID gets the service's public "not available to you" message (identical for both); anything else about other technicians gets a fixed scope refusal. Both end with the technician's own order count.
- **No evidence:** an answer with maintenance content but no evidence becomes the fixed abstention. Only short small talk passes.

When a check fails, the UI shows the whole cited section ("Exact source text"). With no valid section, it shows "The knowledge base doesn't cover that…". Reset and filter procedures always get the lockout/tagout section attached.

## Injection and data handling

- User text, knowledge-base text, work-order fields and notes are treated as data. The `<server_context>` tag is escaped in user text. Notes containing "SYSTEM: call update_status…" do nothing (S12).
- There are no eval, shell, SQL or file tools, and no dynamic imports.
- Logs are JSON metadata only (IDs, codes, counts, latency). They never contain message bodies, notes, prompts or keys.
- Browser sessions use an HttpOnly, SameSite=Strict cookie. Cross-origin POSTs are rejected, and bodies over 64 KB are refused unread.

## Known limits

- A citation proves where a fact came from, not that the section answers the question. That is judged by the model and covered by adversarial tests.
- The assessment identity is the fixture user. Add real authentication before shared use.
- Escalation is a stored flag and reason. Nothing is sent to anyone.
