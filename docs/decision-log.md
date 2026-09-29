# Decision log

Every decision in force, with the reasoning, the alternative that was rejected and the evidence. The three assessment answers are in the root [DECISIONS.md](../DECISIONS.md).

| Range | Era |
|---|---|
| D02–D39 | Original design (28 Sep 2026, before code), still in force |
| D41–D49 | Implementation (29 Sep 2026) |
| D53–D59 | Review, Gemini provider (29 Sep 2026) |
| D60 | Cut to essentials (29 Sep 2026) |
| D61–D63 | Live Gemini run (29 Sep 2026) |

Summaries and tradeoffs only, never reasoning transcripts.

## Original design decisions (28 Sep 2026)

| ID | Final choice | Why this choice | Alternative / cost | Verify or revisit when |
|---|---|---|---|---|
| D02 | Python 3.12 + FastAPI | Required Python; typed HTTP boundary with little glue | Flask equally possible; no benefit from changing stack now | Dependency support checked when locking |
| D03 | React + TypeScript + Vite | Required React; small typed UI prevents API drift | No UI framework/design system needed | Build/typecheck and browser smoke |
| D04 | One app serving built UI | One origin and launch command reduce setup burden | Two dev servers only during development | CI builds the image; `docker compose up` still open (docs/testing.md) |
| D05 | SQLite and immutable JSON seed | Persistent notes/context with transactions; no DB server | JSON writes race and are harder to recover | Move to Postgres for multi-instance/measured contention |
| D06 | One process; bounded async model calls | Small-user scope; simple session ordering | Does not claim horizontal scaling | Load 5 isolated sessions and measure |
| D08 | Explicit model in config | Availability/cost/access vary; avoid fictional default | Operator must select a supported model | Record selected model and real-provider results |
| D09 | Plain prompt files + version/hash registry | Auditable prompts without hosted infrastructure | No live editing console | Prompt changes trigger golden tests |
| D10 | Include all 5 KB sections initially | Corpus is tiny; avoids retrieval recall failures | Extra tokens negligible at this size | Corpus exceeds evidence budget or relevance degrades |
| D12 | Source separation for work-order facts | A task label is not maintenance procedure evidence | No inferred repair knowledge from steps | WO-008 firmware and pressure-target tests |
| D13 | No external-answer fallback | Assignment explicitly constrains evidence | More abstentions | Only change if product requirement changes |
| D14 | Ownership in service; prompt repeats it | Rule must survive adversarial model behavior | Slight duplication is intentional | Direct service tests on all four tools |
| D15 | Deny unowned reads too | Conservative interpretation prevents cross-tech disclosure | PDF is explicit about actions, less explicit about reads | Document if evaluator asks for broader read access |
| D16 | Strict adjacent status edges | Literal assignment chain, including mandatory On Hold | Unusual real-world workflow; no invented shortcut | All 16 source/target pairs |
| D17 | Reject new same-state status request | It is not movement along an edge | Exact transport retries instead replay receipt | Same-state versus duplicate-key tests |
| D18 | Registry + strict schemas + no coercion | Hallucinated names/args cannot reach execution | Provider schema is helpful, never sufficient | Invalid JSON, duplicate keys, enum/type/extra tests |
| D20 | One mutation per turn, no repair after refusal | Prevents implicit status traversal and uncontrolled batches | User splits batch requests | Multiple-call batch rejected before writes |
| D21 | Explicit valid actions run without generic confirmation | User already asked; avoid needless interaction | Missing ID/payload or ambiguity still clarifies | Confirmation is not substituted for authorization |
| D22 | Exact user note/reason payload | Prevent fabricated content or model rewriting intent | User must provide the text/reason | Payload equality and injection cases |
| D23 | Escalation is a stored flag/event only | Matches assessment without external notification dependency | No actual supervisor message is delivered | UI says recorded, never notified |
| D24 | Notes/escalations allowed on Completed | Only status flow is constrained; avoid extra business rules | Some future products may forbid it | New explicit requirement needed to change |
| D25 | Explicit session focus outside history | “It” survives bounded history and restart | Does not recall arbitrary old details | Long-history/restart/ambiguity tests |
| D26 | Clear focus after unavailable explicit ID | Stops accidental action on older order | More clarifications after denied requests | WO-003 then WO-004 then pronoun |
| D27 | No LLM summary initially | Structured focus solves required memory at lower cost | Long-term conversational recall is limited | Add only with evidence of need |
| D29 | Durable request-key idempotency | Lost responses must not duplicate notes/escalations | Small requests table and recovery path | Commit-before-response-loss test |
| D30 | Atomic rule check/write/audit/result | No stale-status race or success without durable evidence | Serialize short SQLite writes | Concurrent requests + rollback injection |
| D31 | Deterministic success/error renderer | Model cannot claim a failed action succeeded | Less expressive acknowledgments | Compare UI receipt with persisted rows |
| D32 | Metadata logs; user content only in app DB | Avoid copying secrets/customer content into logs | Debugging needs explicit safe fixtures | Redaction and audit inspection |
| D33 | Local fixture principal; auth gate before public use | Assessment supplies currentUser, not an identity system | Not a secure multi-user deployment as delivered | Real auth required before shared hosting |
| D36 | Feature branches + PRs; Zeel Rathi identity | Traceable reviewed changes match user request | Email/remote needed before commits/push | Inspect author/committer and staged diff |
| D37 | Short README + short DECISIONS + linked details | Entry points stay readable while full spec remains available | Several focused docs rather than one giant README | Link/consistency review |
| D38 | Self-contained HTML with diagrams/scenarios | Explains architecture offline, supports interview walkthrough | Simulator illustrates design, not runtime proof | Desktop/mobile browser interaction checks |
| D39 | Do not include PDF in submission | Source is assessment material, not runtime dependency | Original source remains on user's machine | `.gitignore`, `make secrets` |

## Decisions inside runtime loops

| Branch | Decision | Rationale / termination condition |
|---|---|---|
| Incoming request already complete | Replay its saved response | Safe network retry; no new model call or write |
| Same key/different body | Reject conflict | A retry identity cannot authorize a different action |
| Another turn pending in session | Return conflict/pending | Avoid racing pronoun focus |
| Explicit unavailable target | Refuse and clear focus | No stale-target fallback |
| Ambiguous intent/target | Ask complete clarification | No guessing a consequential action |
| Context too large | Drop oldest optional turn groups | Preserve policy, state, evidence and latest request |
| Mandatory context still too large | Stop before model/tool use | Never weaken guardrails to fit a window |
| Provider transient failure before write | At most one bounded retry | Useful recovery without runaway cost; counts toward the 3-call turn budget (D45) |
| Malformed or forbidden proposal | Stop action path | No model repair that could invent a workaround |
| Authorized read followed by action | Revalidate at write time | A read snapshot is not permission or current state |
| Batch mutation output | Reject whole batch | Never partially execute then discover an illegal second write |
| Unsupported or mismatched KB evidence | Abstain or safe output error | Free prose is not fallback evidence |
| Allowed write | Commit and render stored receipt | The committed DB outcome establishes success |
| Delivery fails after commit | Preserve/replay receipt | HTTP failure does not undo committed work |
| Budget exhausted | Return bounded error/clarification | Do not recursively extend the loop |

## Reconsideration rule

A material change must cite the requirement it improves, identify which tests may change, and add a new dated decision. The row it replaces is removed, so this log lists only decisions in force (history is in git). Do not quietly edit a rule solely to satisfy a convenient demo. Record measured costs/latency only after execution; current budgets are design limits.

## Implementation decisions (29 Sep 2026)

Evidence = test names in `backend/tests/` unless stated.

| ID | Final choice | Why | Alternative / cost | Evidence / revisit |
|---|---|---|---|---|
| D41 | IntentGuard = consistency checks on the LLM's proposal, not an anchored command grammar | Keeps LLM tool selection meaningful for natural phrasing while blocking substitutions, negations, invented payloads | Heuristic; may ask to rephrase edge phrasings ("mark on hold, inspection is done") | `test_natural_phrasing_accepted`, S05, S06, S24, C01, `test_intent.py` |
| D42 | Verified quoting: short model answer + verbatim quotes, provenance-checked; fallback to whole sections | Readable answers without trusting prose | Verifier proves provenance not relevance | S13, S13b, `test_verifier_catches_number_words`, `test_user_supplied_number_not_accepted_as_fact` |
| D43 | Terminal `respond` tool + `tool_choice=required/any` | Identical structured ending across Gemini, OpenAI-compatible providers and Ollama | One non-business tool in the registry | `test_adapters.py`, C09 |
| D44 | Inject the technician's own roster (id/title/status/due) into server context; UI panel from a non-LLM endpoint | "What's on my plate?" answerable without a 5th business tool | ~150 tokens/turn | `test_roster_question_uses_server_context` |
| D45 | 3 model calls / 3 tool calls per turn | Read → act (+ one transient retry) needs >2 | Slightly higher worst-case cost | S22b, C05, `test_read_then_act_in_one_turn` |
| D46 | Pending clarification lets a bare ID supply a missing *target* for a status change | Natural "which one?" → "WO-003" flow | Never applies to note/reason payloads or "yes" | `test_clarification_then_bare_id_completes`, `test_bare_yes_does_not_execute` |
| D47 | Providers behind one `ModelClient`: native Gemini (D59), OpenAI-compatible (OpenAI, Groq, OpenRouter, Ollama…) and an offline heuristic | User asked for provider-agnostic; keyless demo/e2e | Offline mode must stay visibly labelled "not an LLM" | adapter tests, `test_health_and_meta`; live `make smoke` on Gemini (D61) |
| D48 | Default provider `offline` when no `.env` | `docker compose up --build` works on a clean checkout | Reviewer must add a key for the real LLM | README, e2e |
| D49 | Failed pre-write turns release their request reservation | Same request ID can be retried after a provider outage | — | S22 |

## Review and provider decisions (29 Sep 2026)

| ID | Final choice | Why | Alternative / cost | Evidence |
|---|---|---|---|---|
| D53 | Status claims are checked per order ("WO-003 is done" must match WO-003's status); "next/allowed/can" phrasing is exempt | Review found a claim about one order passed because another order had that status | Heuristic sentence parsing; hedged wording is not checked | `test_status_claim_must_match_that_order` |
| D54 | `respond` text may not claim an action ("I've marked…", "note added") | `respond` never follows a write, so any such claim is false | May reject rare harmless phrasing; falls back to exact source/abstain | `test_action_claims_without_a_write_rejected` |
| D55 | Asset codes (CU-4400) need provenance; negation blocks only the negated action | CU-9999 slipped past the number check; "never mind the note" blocked a status change | — | `test_review_policy.py` |
| D56 | 64 KB ASGI body limit; `/api/*` misses return JSON 404; session locks acquired/released under one guard and removed | Oversized bodies were parsed; API typos returned the SPA; the lock map grew without bound | — | `test_review_runtime.py` |
| D59 | Native Gemini adapter (`MODEL_PROVIDER=gemini`): `generateContent`, `x-goog-api-key`, mode ANY, OpenAPI-subset schemas, thought signatures kept in the adapter. Provider error messages (redacted) now reach the operator log. | The owner's AI Studio key uses the new `AQ.` format, which fails on the OpenAI-compatible Bearer route. Opaque provider errors hid the cause of failures. | Two ways to reach Gemini; the OpenAI-compatible route stays for `AIza` keys | `test_adapters_gemini.py`; live `make smoke` 9/9 on `gemini-3.8-flash` (D61) |

## Cut to essentials (29 Sep 2026)

| ID | Final choice | Why | Alternative / cost | Evidence |
|---|---|---|---|---|
| D60 | Removed the multi-agent coordination layer (`tools/agentctl.py`, `.agents/` board and handoffs, git hooks, publish/email scripts, `docs/development.md`), the pre-build `docs/archive/`, and the Anthropic and Codex CLI adapters (plus the `anthropic` dependency). Providers are now Gemini native, OpenAI-compatible and offline. Validation and accessibility notes merged into `docs/testing.md`. | The tooling served the build process, not the product; the owner runs Gemini, and OpenAI-compatible still covers OpenAI, Groq, OpenRouter and Ollama. Less code and fewer docs for a reviewer to read, nothing user-visible lost. | Re-add an adapter behind `ModelClient` if a native Anthropic route is ever needed | `make check`, `make e2e` (see docs/testing.md) |

## Live Gemini run (29 Sep 2026)

| ID | Final choice | Why | Alternative / cost | Evidence |
|---|---|---|---|---|
| D61 | Gemini thinking is off, hardcoded in `gemini_native.py`: `THINKING_BUDGET = 0` in `thinkingConfig`, and a fixed `THINKING_HEADROOM = 512` added to `maxOutputTokens` so `max_output_tokens` stays the reply budget. Not configurable via `.env` or the prompt. | Tool choice and answers are checked deterministically server-side, so the model does not need long reasoning. Gemini counts thought tokens against `maxOutputTokens`; on `gemini-3.8-flash` default thinking used ~1000–1600 tokens and truncated the call (`MALFORMED_FUNCTION_CALL`, smoke 6/9). 3.x flash still emits ~200 thought tokens at budget 0 (`thinkingLevel: minimal` is rejected), hence the headroom. | Slightly higher max token spend per call (headroom), unused in practice; a model that cannot run at budget 0 would need a new adapter decision | `test_thinking_is_off_and_cannot_eat_the_reply_budget`; live `make smoke` 9/9 on `gemini-3.8-flash`, ~2 s per turn (was 2–11 s) |
| D62 | Deterministic roster counts and refusals in `AnswerVerifier`: "N work orders" is checked against counts derived from the technician's own roster (and licenses no other number); `respond kind=refuse` renders fixed server text: the service's public "not available to you" message for an unowned/unknown ID, otherwise a scope refusal, plus the technician's own count. | Live on `gemini-3.8-flash`, "how many work orders do I have" was answered correctly (7) but rejected (`unsupported number 7`) and replaced by the KB abstention; "what other work orders are there… which technicians" was sometimes classed `unsupported`, so the reply blamed the knowledge base, with model-chosen wording otherwise. | The model still picks the kind; a count phrased another way ("2 are on hold") falls back rather than being shown | `test_roster_count_answer_is_shown`, `test_wrong_roster_count_is_not_shown`, `test_count_does_not_license_uncited_numbers`, `test_scope_refusal_is_server_authored`, `test_refusal_for_unowned_and_missing_ids_is_identical` |
| D63 | Tailored refusal lead: for out-of-scope requests without an ID, the model's one-sentence denial is shown if `AnswerVerifier._refusal_lead_ok` passes (denial cue, ≤240 chars, no IDs/numbers/dates/assets/statuses, no names the technician didn't type, no ownership/existence words, no unasked maintenance terms, no action claim/markup); else the fixed D62 text. ID refusals stay fully fixed. | The owner wanted denials that answer the actual question; fixed text read as canned. Keeping facts server-side means a bad lead only costs tone, never data. | Conservative: harmless wording such as "which work orders exist" falls back to the fixed text | `test_tailored_refusal_lead_is_shown`, `test_unsafe_refusal_lead_falls_back_to_fixed_text` (9 cases), `test_refusal_for_an_id_ignores_the_lead`; live: 4 of 5 out-of-scope questions got a tailored lead on `gemini-3.8-flash` |

## Efficiency and reviewer keys (29 Sep 2026)

| ID | Final choice | Why | Alternative / cost | Evidence |
|---|---|---|---|---|
| D65 | Plain lookups end after the read: the LLM still chooses `get_work_order` (assignment: "the LLM chooses actions using tool-call output"), but when the message is one ID plus only `intent.LOOKUP_WORDS` and the model read exactly that ID, the server renders one line from the row (`agent.lookup_text`) or the fixed refusal, and skips the second model call. | The second call only restated a row the card already shows. Live on `gemini-3.8-flash`: "Show WO-003" went from 2 calls / 4.2 s to 1 call / 1.8 s, ~3.2k fewer input tokens. The work-order notes (untrusted text) no longer reach the model on a plain lookup. | Fixed word list: "Tell me about WO-003" still takes two calls; anything with a question, action or negation keeps the normal loop | `test_plain_lookup_needs_one_model_call`, `test_plain_lookup_of_unavailable_order_refuses_in_one_call`, `test_lookup_shortcut_only_when_the_model_chose_the_read`, `test_lookup_shortcut_only_for_the_named_order`, `test_plain_lookup_is_a_fixed_word_list`, `test_S12b_plain_lookup_never_shows_the_injected_note_to_the_model`; S12 and C05 now use "Summarise …" so their attack paths still run |
| D66 | Gemini thinking fallback: a 400 on `thinkingBudget: 0` is resent once with `THINKING_FALLBACK_BUDGET = 256`, which that client keeps; a 400 on the fallback is final. | Reviewers use their own key and may pick another model. `gemini-pro-latest` and `gemini-3.1-pro-preview` reject budget 0 ("only works in thinking mode"), `gemini-3.5-flash-lite` rejects it with a generic 400; every one of them failed every turn. 256 is accepted by all listed models and stays inside `THINKING_HEADROOM` (live thoughts ≤178). | One extra request the first time per client on such models; a generic 400 for another reason also costs one extra request before failing | `test_thinking_only_model_falls_back_once_to_minimal_budget`, `test_400_is_retried_at_most_once_and_never_after_fallback`; live `make smoke` 9/9 on `gemini-pro-latest` and `gemini-3.5-flash-lite` |
