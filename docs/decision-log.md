# Decision log

Every material decision, with the reasoning, the alternative that was rejected and the evidence. The three assessment answers are in the root [DECISIONS.md](../DECISIONS.md).

| Range | Era |
|---|---|
| D01–D40 | Original design (28 Sep 2026, before code). Rows marked ~~superseded~~ were replaced later. |
| D41–D52 | Implementation (29 Sep 2026) |
| D53–D59 | Review, Codex/Gemini providers, documentation (29 Sep 2026) |
| D60 | Cut to essentials (29 Sep 2026) |

Summaries and tradeoffs only, never reasoning transcripts.

## Original design decisions (28 Sep 2026)

| ID | Final choice | Why this choice | Alternative / cost | Verify or revisit when |
|---|---|---|---|---|
| D01 | Plan and HTML first | User explicitly confirmed delivery scope | A runnable submission is deferred, not claimed complete | Done: implemented 29 Sep |
| D02 | Python 3.12 + FastAPI | Required Python; typed HTTP boundary with little glue | Flask equally possible; no benefit from changing stack now | Dependency support checked when locking |
| D03 | React + TypeScript + Vite | Required React; small typed UI prevents API drift | No UI framework/design system needed | Build/typecheck and browser smoke |
| D04 | One app serving built UI | One origin and launch command reduce setup burden | Two dev servers only during development | Clean Docker startup verified |
| D05 | SQLite and immutable JSON seed | Persistent notes/context with transactions; no DB server | JSON writes race and are harder to recover | Move to Postgres for multi-instance/measured contention |
| D06 | One process; bounded async model calls | Small-user scope; simple session ordering | Does not claim horizontal scaling | Load 5 isolated sessions and measure |
| D07 | ModelClient protocol + one initial provider adapter | Provider SDK details should not reach policy code | Not every model implements equivalent capabilities | Adapter conformance suite before replacement |
| D08 | Explicit model in config | Availability/cost/access vary; avoid fictional default | Operator must select a supported model | Record selected model and real-provider results |
| D09 | Plain prompt files + version/hash registry | Auditable prompts without hosted infrastructure | No live editing console | Prompt changes trigger golden tests |
| D10 | Include all 5 KB sections initially | Corpus is tiny; avoids retrieval recall failures | Extra tokens negligible at this size | Corpus exceeds evidence budget or relevance degrades |
| D11 | ~~Render complete cited sections~~ superseded by D42 | Code can prevent invented technical prose and omitted cautions | Less conversational; relevance remains probabilistic | Covered/uncovered/mixed adversarial evaluation |
| D12 | Source separation for work-order facts | A task label is not maintenance procedure evidence | No inferred repair knowledge from steps | WO-008 firmware and pressure-target tests |
| D13 | No external-answer fallback | Assignment explicitly constrains evidence | More abstentions | Only change if product requirement changes |
| D14 | Ownership in service; prompt repeats it | Rule must survive adversarial model behavior | Slight duplication is intentional | Direct service tests on all four tools |
| D15 | Deny unowned reads too | Conservative interpretation prevents cross-tech disclosure | PDF is explicit about actions, less explicit about reads | Document if evaluator asks for broader read access |
| D16 | Strict adjacent status edges | Literal assignment chain, including mandatory On Hold | Unusual real-world workflow; no invented shortcut | All 16 source/target pairs |
| D17 | Reject new same-state status request | It is not movement along an edge | Exact transport retries instead replay receipt | Same-state versus duplicate-key tests |
| D18 | Registry + strict schemas + no coercion | Hallucinated names/args cannot reach execution | Provider schema is helpful, never sufficient | Invalid JSON, duplicate keys, enum/type/extra tests |
| D19 | ~~Conservative deterministic intent binding~~ superseded by D41 | Stops legal-but-unrequested intermediate changes | Narrow mutation phrasing; clarify unsupported language | Negated/hypothetical/compound/alternate-status tests |
| D20 | One mutation per turn, no repair after refusal | Prevents implicit status traversal and uncontrolled batches | User splits batch requests | Multiple-call batch rejected before writes |
| D21 | Explicit valid actions run without generic confirmation | User already asked; avoid needless interaction | Missing ID/payload or ambiguity still clarifies | Confirmation is not substituted for authorization |
| D22 | Exact user note/reason payload | Prevent fabricated content or model rewriting intent | User must provide the text/reason | Payload equality and injection cases |
| D23 | Escalation is a stored flag/event only | Matches assessment without external notification dependency | No actual supervisor message is delivered | UI says recorded, never notified |
| D24 | Notes/escalations allowed on Completed | Only status flow is constrained; avoid extra business rules | Some future products may forbid it | New explicit requirement needed to change |
| D25 | Explicit session focus outside history | “It” survives bounded history and restart | Does not recall arbitrary old details | Long-history/restart/ambiguity tests |
| D26 | Clear focus after unavailable explicit ID | Stops accidental action on older order | More clarifications after denied requests | WO-003 then WO-004 then pronoun |
| D27 | No LLM summary initially | Structured focus solves required memory at lower cost | Long-term conversational recall is limited | Add only with evidence of need |
| D28 | ~~Two model attempts/two tools maximum~~ superseded by D45 | Enough for read plus action; prevents unbounded loops | Large comparisons ask to narrow | Counters include retries and bad calls |
| D29 | Durable request-key idempotency | Lost responses must not duplicate notes/escalations | Small requests table and recovery path | Commit-before-response-loss test |
| D30 | Atomic rule check/write/audit/result | No stale-status race or success without durable evidence | Serialize short SQLite writes | Concurrent requests + rollback injection |
| D31 | Deterministic success/error renderer | Model cannot claim a failed action succeeded | Less expressive acknowledgments | Compare UI receipt with persisted rows |
| D32 | Metadata logs; user content only in app DB | Avoid copying secrets/customer content into logs | Debugging needs explicit safe fixtures | Redaction and audit inspection |
| D33 | Local fixture principal; auth gate before public use | Assessment supplies currentUser, not an identity system | Not a secure multi-user deployment as delivered | Real auth required before shared hosting |
| D34 | ~~Test fake provider first, then actual API~~ superseded by D47 | Deterministic failure coverage without token costs | Fake tests cannot prove SDK integration | Real model tool/KB smoke required for completion |
| D35 | Freeze contracts then parallel implementation | Independent UI/domain/agent tasks reduce elapsed time | Shared files need one integration owner | Handoffs reconcile before merge |
| D36 | Feature branches + PRs; Zeel Rathi identity | Traceable reviewed changes match user request | Email/remote needed before commits/push | Inspect author/committer and staged diff |
| D37 | Short README + short DECISIONS + linked details | Entry points stay readable while full spec remains available | Several focused docs rather than one giant README | Link/consistency review |
| D38 | Self-contained HTML with diagrams/scenarios | Explains architecture offline, supports interview walkthrough | Simulator illustrates design, not runtime proof | Desktop/mobile browser interaction checks |
| D39 | Do not include PDF in submission | Source is assessment material, not runtime dependency | Original source remains on user's machine | Archive manifest and secret/content review |
| D40 | Lock dependencies only during implementation | Reproducibility must reflect actual installed/tested versions | Plan has version targets, not fabricated lockfiles | Clean locked installs and provider smoke |

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
| Provider transient failure before write | At most one bounded retry | Useful recovery without runaway cost; total attempt cap 2 |
| Malformed or forbidden proposal | Stop action path | No model repair that could invent a workaround |
| Authorized read followed by action | Revalidate at write time | A read snapshot is not permission or current state |
| Batch mutation output | Reject whole batch | Never partially execute then discover an illegal second write |
| Unsupported or mismatched KB evidence | Abstain or safe output error | Free prose is not fallback evidence |
| Allowed write | Commit and render stored receipt | The committed DB outcome establishes success |
| Delivery fails after commit | Preserve/replay receipt | HTTP failure does not undo committed work |
| Budget exhausted | Return bounded error/clarification | Do not recursively extend the loop |

## Reconsideration rule

A material change must cite the requirement it improves, identify which tests may change, and append a new dated decision superseding the prior ID. Do not quietly edit a rule solely to satisfy a convenient demo. Record measured costs/latency only after execution; current budgets are design limits.

## Implementation decisions (29 Sep 2026)

These supersede earlier IDs where noted. Evidence = test names in `backend/tests/` unless stated.

| ID | Final choice | Why | Alternative / cost | Evidence / revisit |
|---|---|---|---|---|
| D41 (supersedes D19) | IntentGuard = consistency checks on the LLM's proposal, not an anchored command grammar | Keeps LLM tool selection meaningful for natural phrasing while blocking substitutions, negations, invented payloads | Heuristic; may ask to rephrase edge phrasings ("mark on hold, inspection is done") | `test_natural_phrasing_accepted`, S05, S06, S24, C01, `test_intent.py` |
| D42 (supersedes D11) | Verified quoting: short model answer + verbatim quotes, provenance-checked; fallback to whole sections | Readable answers without trusting prose | Verifier proves provenance not relevance | S13, S13b, `test_verifier_catches_number_words`, `test_user_supplied_number_not_accepted_as_fact` |
| D43 | Terminal `respond` tool + `tool_choice=required/any` | Identical structured ending across OpenAI, Anthropic, Gemini-compat, Ollama | One non-business tool in the registry | `test_adapters.py`, C09 |
| D44 | Inject the technician's own roster (id/title/status/due) into server context; UI panel from a non-LLM endpoint | "What's on my plate?" answerable without a 5th business tool | ~150 tokens/turn | `test_roster_question_uses_server_context` |
| D45 (supersedes D28) | 3 model calls / 3 tool calls per turn | Read → act (+ one transient retry) needs >2 | Slightly higher worst-case cost | S22b, C05, `test_read_then_act_in_one_turn` |
| D46 | Pending clarification lets a bare ID supply a missing *target* for a status change | Natural "which one?" → "WO-003" flow | Never applies to note/reason payloads or "yes" | `test_clarification_then_bare_id_completes`, `test_bare_yes_does_not_execute` |
| D47 (supersedes D34/D7) | Providers: OpenAI-compatible adapter (covers OpenAI, Gemini, Groq, OpenRouter, Ollama…) + native Anthropic + offline heuristic | User asked for provider-agnostic; keyless demo/e2e | Offline mode must stay visibly labelled "not an LLM" | adapter tests, `test_health_and_meta` |
| D48 | Default provider `offline` when no `.env` | `docker compose up --build` works on a clean checkout | Reviewer must add a key for the real LLM | README, e2e |
| D49 | Failed pre-write turns release their request reservation | Same request ID can be retried after a provider outage | — | S22 |
| D50 (superseded by D60) | Agent coordination via `tools/agentctl.py` (claims in git common dir, path overlap, handoffs) + generated pointer files | Many agents/providers in parallel without a server | Local-machine atomicity; cross-machine relies on pushed `agent/*` branches | `tools/tests/test_agentctl.py` |
| D51 | Commit identity `Zeel Rathi <zeel.rathi@placeholder.invalid>` until the verified email is supplied | Plan forbids inventing an email; placeholder is obviously non-real | Resolved 29 Sep 2026: rewritten to the verified address before the first push | T16 done |
| D52 | Docker build verified by reproducing the image layout (hash-locked pip install + built UI + env) because Docker Hub is blocked in the build sandbox | Honest partial evidence | Real `docker compose build` still to run on an unrestricted machine | docs/validation.md |

## Review, provider and documentation decisions (29 Sep 2026)

| ID | Final choice | Why | Alternative / cost | Evidence |
|---|---|---|---|---|
| D53 | Status claims are checked per order ("WO-003 is done" must match WO-003's status); "next/allowed/can" phrasing is exempt | Review found a claim about one order passed because another order had that status | Heuristic sentence parsing; hedged wording is not checked | `test_status_claim_must_match_that_order` |
| D54 | `respond` text may not claim an action ("I've marked…", "note added") | `respond` never follows a write, so any such claim is false | May reject rare harmless phrasing; falls back to exact source/abstain | `test_action_claims_without_a_write_rejected` |
| D55 | Asset codes (CU-4400) need provenance; negation blocks only the negated action | CU-9999 slipped past the number check; "never mind the note" blocked a status change | — | `test_review_policy.py` |
| D56 | 64 KB ASGI body limit; `/api/*` misses return JSON 404; session locks acquired/released under one guard and removed | Oversized bodies were parsed; API typos returned the SPA; the lock map grew without bound | — | `test_review_runtime.py` |
| D57 (superseded by D60) | `MODEL_PROVIDER=codex`: one `codex exec` per model step, read-only sandbox, empty temp dir, `--ephemeral`, output schema forcing `{tool, arguments_json}` | Lets the owner test with a real LLM through a ChatGPT login, no API key | Slow (a process per step), local only, output parsed from the CLI; same server checks apply | `test_codex.py` incl. full pipeline through a fake binary |
| D58 (superseded by D60) | Agent config reduced to `AGENTS.md` + one-line `CLAUDE.md`; other tools' configs generated on demand (`agentctl adapters`); pre-build docs moved to `docs/archive/`; hooks in `tools/githooks` | AGENTS.md is read natively by most agents; eight pointer files and dot-folders were clutter nobody used | Gemini/Aider/Cline users run one command | `test_adapters_add_and_remove_on_demand`, `agentctl doctor` |
| D59 | Native Gemini adapter (`MODEL_PROVIDER=gemini`): `generateContent`, `x-goog-api-key`, mode ANY, OpenAPI-subset schemas, thought signatures kept in the adapter. Provider error messages (redacted) now reach the operator log. | The owner's AI Studio key uses the new `AQ.` format, which fails on the OpenAI-compatible Bearer route. The first live smoke test failed with an opaque `NotFoundError`. | Two ways to reach Gemini; the OpenAI-compatible route stays for `AIza` keys | `test_adapters_gemini.py`; a live run by the owner is still pending (the build sandbox can't reach Google) |

## Cut to essentials (29 Sep 2026)

| ID | Final choice | Why | Alternative / cost | Evidence |
|---|---|---|---|---|
| D60 (supersedes D50, D57, D58; narrows D47) | Removed the multi-agent coordination layer (`tools/agentctl.py`, `.agents/` board and handoffs, git hooks, publish/email scripts, `docs/development.md`), the pre-build `docs/archive/`, and the Anthropic and Codex CLI adapters (plus the `anthropic` dependency). Providers are now Gemini native, OpenAI-compatible and offline. Validation and accessibility notes merged into `docs/testing.md`. | The tooling served the build process, not the product; the owner runs Gemini, and OpenAI-compatible still covers OpenAI, Groq, OpenRouter and Ollama. Less code and fewer docs for a reviewer to read, nothing user-visible lost. | Re-add an adapter behind `ModelClient` if a native Anthropic route is ever needed | `make check`, `make e2e`, live `make smoke` (see docs/testing.md) |
