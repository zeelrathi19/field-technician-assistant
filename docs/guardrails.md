# Guardrails and execution contract

This is an implementation specification. “Required” below means required by the assignment; “added” means a deliberately small safeguard chosen for this design. No model message, retrieved passage, tool result, user note, or conversation summary is an authority for changing these rules.

## Trust and authority

| Boundary | Enforcement and reason | Source |
|---|---|---|
| Logged-in technician | Backend loads `currentUser.id` from trusted configuration/seed context. Never accept a replacement identity, role, or `assignedTech` from chat or tool arguments. A public deployment must obtain identity from real authentication. | Required ownership rule; server identity is the implementation choice |
| Owned work orders | Check `assignedTech == currentUser.id` inside the service immediately before every operation, including reads. Deny access to another technician's order without returning its details. | Mutations required; read restriction added because “act” is ambiguous |
| Status sequence | Exactly one forward edge: `Open → In Progress`, `In Progress → On Hold`, `On Hold → Completed`. Same-state, backwards, and skipped transitions fail. `Completed` has no outgoing edge. | Required; explicit same-state rejection follows strict movement interpretation |
| Tool input | Dispatcher uses an explicit four-name allowlist and strict typed argument models. Reject unknown names, extra fields, wrong types, invalid enums, empty required text, oversized values, and malformed JSON before execution. | Name/malformed rejection required; bounds added |
| Knowledge | Technical guidance is rendered only from approved KB sections. Missing information receives an explicit abstention. The model selects section IDs or abstains; it cannot supply technical answer prose to render. | Grounding required; extractive rendering is the implementation choice |
| Tool outcomes | Backend supplies the final success/error message from the actual operation result. An LLM assertion cannot establish success. | Added to prevent invented action results |
| Conversation | Store active order and recent turns by server-owned user/session identity. Pronouns use a successfully resolved owned active order. No unique referent means ask a clarifying question before execution. | Multi-turn context required; isolation/ambiguity behavior added |

The prompt explains these rules to reduce failed proposals. The service enforces them because prompts are not an authorization boundary. Work-order `steps` and notes describe operational data; they are not instructions to the assistant and never override the KB or execution policy.

## Tool contract

Expose only these model-visible tools. Use `additionalProperties: false` and exact status enum values. IDs follow the fixture form `WO-` plus three digits; centralize this rule so a later ID-format change affects one validator.

| Tool | Model arguments | Effects |
|---|---|---|
| `get_work_order` | `id: string` | Read the owned order; a successful explicit lookup may set conversation focus. |
| `update_status` | `id: string`, `status: enum` | Check ownership and the current persisted status, then apply one legal edge. |
| `add_note` | `id: string`, `text: string` | Append a nonempty note with authenticated author and server timestamp. |
| `escalate` | `id: string`, `reason: string` | Record escalation flag/reason, author, and timestamp. Does not change status or send email. |

Trim strings, reject empty values, and apply configurable limits (suggested initial limits: note 2,000 characters; reason 500 characters; user message 8,000 characters). Never coerce a number into an ID or a string into an object. Tool arguments cannot include `currentUser`, permissions, timestamps, persistence paths, SQL, or an idempotency key.

Return a consistent service result with `ok`, `code`, `message`, and permitted `data`. Suggested codes: `UNKNOWN_TOOL`, `INVALID_ARGUMENTS`, `ACCESS_DENIED_OR_NOT_FOUND`, `INVALID_TRANSITION`, `CLARIFICATION_REQUIRED`, `CONFLICT`, `PROVIDER_UNAVAILABLE`. Combine unavailable/unauthorized results at the UI boundary to avoid disclosing other users' orders; internal audit events can distinguish them.

## One turn, one intentional mutation

1. Accept a bounded user message under a valid conversation. A write requires an actual action request in the current user turn; an FAQ, quotation, retrieved instruction, or model suggestion is insufficient.
2. Resolve an explicit order reference or an unambiguous active order. A blocked/unknown explicit ID invalidates prior focus for subsequent pronouns; never silently fall back to an older order.
3. Resolve the intended action and supplied payload. “Mark it complete” means target status `Completed`; it does not authorize `On Hold` or an invented multi-step workaround. A conservative status alias map can support `done`/`complete` → `Completed`, `start` → `In Progress`, and `hold` → `On Hold`. Ambiguity requires clarification. Do not invent a reason or note the user did not supply; offer a proposed value for the user to confirm if needed.
4. The LLM proposes a structured call. The orchestrator verifies that it matches the resolved action/target; the dispatcher validates schema; the service validates business rules. Prompt-only intent checks are insufficient. Use narrow, explicit supported action patterns for the initial implementation and clarify unsupported compound phrasing rather than building a second general-purpose agent.
5. Permit bounded read calls, but at most one mutation per turn. A mutation proposal rejected by policy ends action processing for that turn. Never ask the LLM to “repair” a forbidden transition through alternate mutations. For multiple requested writes, ask the user to split them or choose one.
6. Persist the result, then render a deterministic acknowledgment. On denial, explain the allowed next status without changing anything. On timeout or conflict, say what is known; never infer a write succeeded.

A new user turn explicitly requesting an allowed next status is valid. The status rule does not establish that physical work happened; the app records the technician's request and does not fabricate inspection evidence. Do not add undisclosed prerequisite rules beyond the assignment.

## Grounded answers and prompt injection

- Parse `knowledge.md` into stable sections `kb-1` through `kb-5`, preserving source title and original text. Initially include all five complete sections because the fixture is only about 2.5 KB; use the retrieval interface for a future subset only when evaluated context limits require it. No embeddings or vector database are needed.
- Return a whole relevant section, or a curated complete block that retains its associated warnings and prerequisites. In the initial version, whole sections minimize accidental removal of safety qualifiers.
- A model can nominate only valid retrieved section IDs and a coverage result; validate IDs in code. The renderer copies source text with visible source title/section citations. Ignore arbitrary model-provided answer text. This prevents invented technical facts; it does **not** mathematically prove the selected section answers the question, so evaluate relevance and abstention separately.
- For a CU reset, preserve the 60-second wait, 5-second RESET hold, 2-minute check, escalation condition, and maximum 3 consecutive resets. Include the lockout section where the requested work involves powered equipment servicing; do not invent missing electrical instructions.
- Unsupported requests such as firmware flashing, torque settings, refrigerant pressure targets, or part prices receive: “The knowledge base does not cover that, so I can’t provide a procedure/value.” For a mixed question, show supported sections and explicitly identify missing coverage.
- Work-order facts come only from successful authorized tool results. Keep their provenance separate from maintenance guidance. A work order saying “check firmware version” does not establish how to install firmware.
- Treat user chat, notes, work-order text, and KB text as untrusted content. Never interpret embedded “ignore rules”, tool JSON, role markers, or instructions to exfiltrate configuration as executable commands. Escape rendered text in React and avoid raw HTML rendering.
- Retrieved text advising escalation is guidance, not permission to execute a tool. “When should I escalate?” produces an answer. “Escalate WO-006 because exposed wiring was found” authorizes a write if ownership and schemas pass.
- Unsupported advice about hazardous work receives abstention plus any directly relevant supplied safety section. Avoid adding technical safety procedures absent from the supplied source.

## Memory, atomicity, and retries

The authoritative order state lives in SQLite, never a summary or model message. Store per-conversation active order, recent turns, and unresolved clarification state. Session isolation is mandatory even for the local demo. A shared seed user is acceptable for local assessment only; do not describe it as production authentication.

Use one transaction for ownership recheck, current-status check, write, audit event, and completed request result. Acquire a SQLite write transaction before the read/check/write sequence, or use a versioned conditional update with a conflict response. A single local worker and short transactions are enough; no distributed locks or event bus are needed. Do not hold a transaction open during a model API call.

The client sends a unique request ID in the chat request envelope. Backend scopes it to the authenticated user and conversation, stores a hash of the request, and replays the saved result for an exact retry. Reusing the ID with different content returns `CONFLICT`. The model cannot set or modify this key. A pending duplicate waits briefly or returns a retriable in-progress result; it must never launch a second mutation. Distinct user request IDs represent distinct requests and may legitimately add identical note text.

For status updates, compare any observed order version at execution to detect intervening changes. On conflict, return the fresh permitted state and require a new user decision. On restart after a commit but before delivery, replay the persisted result. Do not automatically retry a mutation after an uncertain outcome without checking its request record.

Log structured operational metadata: request/conversation correlation, tool name, order ID, policy result, latency, and model/token counters. Exclude API keys, authorization headers, raw prompts, user note bodies, and complete chats from application logs by default. Notes/chats deliberately stored in the application database are user data with documented retention/reset behavior. Separate concise decision records from private model reasoning; never request or store chain-of-thought.

## Explicit scope and ambiguities

- The mandated chain forces `In Progress → On Hold → Completed` even if a real service workflow would differ. Implement it literally and document that choice.
- Assignment ownership wording does not explicitly settle reads. This design denies unowned reads as an additional least-privilege safeguard.
- Escalation persistence, duplicate behavior, and note metadata are unspecified. This design persists each accepted explicit escalation event and a current flag without contacting a real supervisor service; explain this in the UI/README.
- PDF asks for a short `DECISIONS.md`. Put its three required answers there; keep this longer specification and acceptance suite separate.
