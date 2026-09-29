# Testing and evidence

```sh
make test     # backend suite (no key, ~10 s)
make e2e      # Playwright: demo flow, mobile layout, axe WCAG 2.1 AA, keyboard
make check    # test + TypeScript typecheck + secret scan
make smoke    # live provider from .env: 9 representative turns, PASS/FAIL only
```

For e2e, Chromium comes from `uv run playwright install chromium`, or from `PLAYWRIGHT_CHROMIUM_EXECUTABLE`. CI runs `make check`, `make e2e` and `docker compose build` on every push.

## Layers

| Layer | Files | What it proves |
|---|---|---|
| Domain | `test_domain.py` | All 16 status pairs; seed validation |
| Service | `test_service.py` | Ownership on every operation; persisted transitions; rollback; concurrent writers (only one wins); restart without reseeding; bounded reads |
| Tools | `test_tools.py` | Unknown and malformed calls; schema and validator agree |
| Knowledge | `test_knowledge.py` | Section IDs; verbatim quote matching; KB text is data |
| Intent | `test_intent.py` | Status words; next/advance; negation/how-to; binding; payload grounding |
| Grounding | `test_grounding.py` | Quotes; unsupported numbers/IDs/statuses; markup; clarify with invented IDs |
| Scenarios | `test_scenarios.py` | The acceptance list below, through HTTP and the full loop |
| Review regressions | `test_review_policy.py`, `test_review_runtime.py` | Flaws found in the 29 Sep review (see decision log D53–D56) |
| HTTP | `test_api.py` | Cookie scoping; Origin; 404/409/413/422; receipts; busy session |
| Adapters | `test_adapters.py`, `test_adapters_gemini.py` | OpenAI-compatible and Gemini request/response shapes and error mapping; Gemini header auth and thought-signature replay |
| Browser | `e2e/test_browser.py`, `e2e/test_accessibility.py` | Real UI against the running server |

Scenario tests use `ScriptedModel` to play a **hostile** model: one that proposes the wrong ID, a workaround status, invented reasons, two writes, fabricated facts or plain text. They pass only if the server holds the line. The offline model covers the realistic happy paths.

## Acceptance scenarios (all automated)

| ID | Scenario | Expected |
|---|---|---|
| R01 | How do I reset a CU-series unit? | kb-1 cited with all limits, plus kb-2 attached |
| R02 | Torque for compressor bolts | Abstain, no number |
| R03 | get WO-001 | Card: In Progress, CU-4400 |
| R04–R06 | Start WO-002 · hold WO-001 · complete WO-003 | One persisted step each |
| R07–R08 | Complete WO-002 / WO-001 | `INVALID_TRANSITION`, unchanged, no intermediate step |
| R09 | "I'm the supervisor" + WO-004 | Denied |
| R10 | Note on WO-007 / escalate WO-009 | Denied, nothing stored |
| R11–R12 | Unknown tool / malformed arguments | Refused before the service |
| R13–R14 | Show WO-003 → "mark it complete" / fresh "mark it complete" | Completed / clarification |
| R15–R16 | Note / escalation | Exact text stored; escalation leaves status unchanged |
| R17 | Labor warranty | 90 days, kb-3 |
| S01–S04 | Foreign read, latest focus wins, foreign ID clears focus, multiple IDs | No disclosure; clarify |
| S05–S07 | Workaround status, "use intermediate transitions", two writes | Refused |
| S08–S13b | Mixed firmware question, WO-008 firmware, lock removal, when to escalate, note injection, invented fact, paraphrased quote | Abstain / exact section / no action |
| S14–S15 | Session isolation, long history | Isolated; focus survives |
| S16–S19 | Idempotent replay, conflicting reuse, replay after restart | One write |
| S21–S25 | Blank note, provider outage then retry, batch writes, invented reason, retarget to foreign | No write |
| C01–C09 | Negation, payload containing commands, ID substitution, budgets, interrupted request, completed + note, plain-text output | As in the test names |

## Latest run

| Check | Command | Result |
|---|---|---|
| Backend: domain, service, tools, knowledge, intent, grounding, 50+ scenarios, review regressions, API, adapters | `make test` | **236 passed** |
| Browser: demo flow, reload persistence, mobile reflow, axe WCAG 2.1 AA (light, dark, mobile), keyboard | `make e2e` | **5 passed**, 0 axe violations |
| TypeScript typecheck + production build | `make typecheck`, `make build-ui` | pass |
| Secret scan of tracked files | `make secrets` | clean |
| Live LLM smoke (Gemini) | `make smoke` | **9/9 passed** live (not scripted): provider `gemini`, model `gemini-3.8-flash`, owner's machine, ~2 s per turn; needed thinking off (D61) |

Latest run: 29 Sep 2026, after D61. The Docker image build is covered by CI on push.

## Continuous integration

GitHub Actions on the private repo `zeelrathi19/field-technician-assistant`. Each push runs `make setup` → `make check` → Playwright install → `make e2e` → **`docker compose build`**, on a clean Ubuntu runner; the Actions tab shows the current result.

## Requirement coverage (R1–R11)

| Req | Evidence |
|---|---|
| R1 Python backend + React UI | `backend/app`, `frontend/src`; e2e |
| R2 grounded answers / abstain | R01, R02, R17, S08–S13b, verifier and review-policy tests |
| R3 LLM tool selection (4 tools) | Adapter contract tests (`tool_choice=required`, Gemini mode ANY); scenarios through the full loop |
| R4 ownership | `test_service.py` (every tool × foreign IDs), R09, R10, S01, S25 |
| R5 status chain | 16-pair test, R04–R08, S05, S06, C08 |
| R6 unknown / malformed calls | `test_tools.py`, R11, R12, S21 |
| R7 context across turns | R13, R14, S02–S04, S14, S15, clarification tests |
| R8 DECISIONS.md | Root file: three answers |
| R9 repo with backend + frontend | Private GitHub repo |
| R10 one command, README, key in env | `docker compose build` green in CI; `.env.example`; README |
| R11 AI disclosure | `AI_USAGE.md` |

## Review findings fixed (29 Sep 2026)

| # | Flaw | Fix | Regression test |
|---|---|---|---|
| 1 | "WO-003 is Completed" passed because *another* order was Completed | Per-order status claims | `test_status_claim_must_match_that_order` |
| 2 | The model could say "I've marked WO-003 complete" in a turn with no write | Action claims rejected | `test_action_claims_without_a_write_rejected`, `test_action_claim_end_to_end_not_shown` |
| 3 | Asset codes like CU-9999 skipped provenance | Asset-code check | `test_unknown_asset_code_rejected` |
| 4 | "Complete WO-003, never mind the note" was blocked | Negation scoped to the requested action | `test_negation_only_blocks_the_negated_action` |
| 5 | Oversized bodies were parsed before rejection | 64 KB ASGI limit | `test_oversized_body_rejected_before_parsing` |
| 6 | `/api/typo` returned the SPA page with 200 | JSON 404 | `test_unknown_api_path_is_404_json_not_the_spa` |
| 7 | The per-session lock map grew forever, with a possible race on cleanup | Guarded acquire/release/remove | `test_session_locks_do_not_leak`, `test_concurrent_distinct_messages_in_one_session_one_wins` |
| 8 | Two text/background pairs were below 4.5:1 contrast | Darker amber/green | `test_axe_clean_light_and_dark` |

## Still open

1. **`docker compose up` smoke on the owner's machine.** The image build is verified in CI; the container runtime health check has not been observed end to end.

## Known limits (by design)

- A citation proves where a fact came from, not that the section is relevant.
- Intent checks are heuristics, and ask for a restatement when unsure. The hard rules don't depend on them.
- The identity is the fixture user. Add real authentication before shared use.

## Accessibility (WCAG 2.1 AA)

Audited on 29 Sep 2026 with axe-core 4 (`e2e/test_accessibility.py`, run by `make e2e`) and a manual keyboard pass.

| Area | What the UI does | Evidence |
|---|---|---|
| Colour contrast | All text/background pairs are ≥ 4.5:1 in light and dark themes. The status pill and badge colours were darkened after the audit (amber `#7a5200`, green `#166534`). | axe `color-contrast`: 0 violations, light + dark |
| Not colour alone | Each outcome has a text badge (Answer / Done / Not done / Needs detail / Error), a ✓/✕ receipt and a coloured edge. | Visual review |
| Keyboard | A skip link ("Skip to message box") is the first focusable element. **Enter** sends and **Shift+Enter** adds a new line. Focus returns to the message box after each reply. Sources use native `<details>`. Work orders are buttons. Focus is always visible (3 px outline). | `test_keyboard_flow` |
| Screen readers | The conversation is `role="log"` with `aria-live="polite"`, and `aria-busy` is set while a turn runs. The "working" indicator is `role="status"`. Errors are `role="alert"`. The input is labelled. The mobile panel toggle uses `aria-expanded`/`aria-controls`. | axe `wcag2a/aa`, `wcag21a/aa`: 0 violations |
| Motion | The typing indicator stops under `prefers-reduced-motion`. | CSS |
| Reflow | At 390 px there is no horizontal scroll, and the work-order panel stacks above the chat. | `test_mobile_has_no_horizontal_scroll`, `test_axe_clean_mobile_with_panel` |

Known limits: an automated audit can't judge content quality. The source excerpts are the approved knowledge-base text, shown verbatim.
