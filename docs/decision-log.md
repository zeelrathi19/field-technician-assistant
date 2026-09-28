# Decision register

Status: accepted **design choices**, pending implementation evidence. These are concise decision summaries and tradeoffs, not private reasoning transcripts. The assessment's three answers stay in the short root `DECISIONS.md`.

| ID | Final choice | Why this choice | Alternative / cost | Verify or revisit when |
|---|---|---|---|---|
| D01 | Plan and HTML first | User explicitly confirmed delivery scope | A runnable submission is deferred, not claimed complete | User requests implementation |
| D02 | Python 3.12 + FastAPI | Required Python; typed HTTP boundary with little glue | Flask equally possible; no benefit from changing stack now | Dependency support checked when locking |
| D03 | React + TypeScript + Vite | Required React; small typed UI prevents API drift | No UI framework/design system needed | Build/typecheck and browser smoke |
| D04 | One app serving built UI | One origin and launch command reduce setup burden | Two dev servers only during development | Clean Docker startup verified |
| D05 | SQLite and immutable JSON seed | Persistent notes/context with transactions; no DB server | JSON writes race and are harder to recover | Move to Postgres for multi-instance/measured contention |
| D06 | One process; bounded async model calls | Small-user scope; simple session ordering | Does not claim horizontal scaling | Load 5 isolated sessions and measure |
| D07 | ModelClient protocol + one initial provider adapter | Provider SDK details should not reach policy code | Not every model implements equivalent capabilities | Adapter conformance suite before replacement |
| D08 | Explicit model in config | Availability/cost/access vary; avoid fictional default | Operator must select a supported model | Record selected model and real-provider results |
| D09 | Plain prompt files + version/hash registry | Auditable prompts without hosted infrastructure | No live editing console | Prompt changes trigger golden tests |
| D10 | Include all 5 KB sections initially | Corpus is tiny; avoids retrieval recall failures | Extra tokens negligible at this size | Corpus exceeds evidence budget or relevance degrades |
| D11 | Render complete cited sections | Code can prevent invented technical prose and omitted cautions | Less conversational; relevance remains probabilistic | Covered/uncovered/mixed adversarial evaluation |
| D12 | Source separation for work-order facts | A task label is not maintenance procedure evidence | No inferred repair knowledge from steps | WO-008 firmware and pressure-target tests |
| D13 | No external-answer fallback | Assignment explicitly constrains evidence | More abstentions | Only change if product requirement changes |
| D14 | Ownership in service; prompt repeats it | Rule must survive adversarial model behavior | Slight duplication is intentional | Direct service tests on all four tools |
| D15 | Deny unowned reads too | Conservative interpretation prevents cross-tech disclosure | PDF is explicit about actions, less explicit about reads | Document if evaluator asks for broader read access |
| D16 | Strict adjacent status edges | Literal assignment chain, including mandatory On Hold | Unusual real-world workflow; no invented shortcut | All 16 source/target pairs |
| D17 | Reject new same-state status request | It is not movement along an edge | Exact transport retries instead replay receipt | Same-state versus duplicate-key tests |
| D18 | Registry + strict schemas + no coercion | Hallucinated names/args cannot reach execution | Provider schema is helpful, never sufficient | Invalid JSON, duplicate keys, enum/type/extra tests |
| D19 | Conservative deterministic intent binding | Stops legal-but-unrequested intermediate changes | Narrow mutation phrasing; clarify unsupported language | Negated/hypothetical/compound/alternate-status tests |
| D20 | One mutation per turn, no repair after refusal | Prevents implicit status traversal and uncontrolled batches | User splits batch requests | Multiple-call batch rejected before writes |
| D21 | Explicit valid actions run without generic confirmation | User already asked; avoid needless interaction | Missing ID/payload or ambiguity still clarifies | Confirmation is not substituted for authorization |
| D22 | Exact user note/reason payload | Prevent fabricated content or model rewriting intent | User must provide the text/reason | Payload equality and injection cases |
| D23 | Escalation is a stored flag/event only | Matches assessment without external notification dependency | No actual supervisor message is delivered | UI says recorded, never notified |
| D24 | Notes/escalations allowed on Completed | Only status flow is constrained; avoid extra business rules | Some future products may forbid it | New explicit requirement needed to change |
| D25 | Explicit session focus outside history | “It” survives bounded history and restart | Does not recall arbitrary old details | Long-history/restart/ambiguity tests |
| D26 | Clear focus after unavailable explicit ID | Stops accidental action on older order | More clarifications after denied requests | WO-003 then WO-004 then pronoun |
| D27 | No LLM summary initially | Structured focus solves required memory at lower cost | Long-term conversational recall is limited | Add only with evidence of need |
| D28 | Two model attempts/two tools maximum | Enough for read plus action; prevents unbounded loops | Large comparisons ask to narrow | Counters include retries and bad calls |
| D29 | Durable request-key idempotency | Lost responses must not duplicate notes/escalations | Small requests table and recovery path | Commit-before-response-loss test |
| D30 | Atomic rule check/write/audit/result | No stale-status race or success without durable evidence | Serialize short SQLite writes | Concurrent requests + rollback injection |
| D31 | Deterministic success/error renderer | Model cannot claim a failed action succeeded | Less expressive acknowledgments | Compare UI receipt with persisted rows |
| D32 | Metadata logs; user content only in app DB | Avoid copying secrets/customer content into logs | Debugging needs explicit safe fixtures | Redaction and audit inspection |
| D33 | Local fixture principal; auth gate before public use | Assessment supplies currentUser, not an identity system | Not a secure multi-user deployment as delivered | Real auth required before shared hosting |
| D34 | Test fake provider first, then actual API | Deterministic failure coverage without token costs | Fake tests cannot prove SDK integration | Real model tool/KB smoke required for completion |
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
