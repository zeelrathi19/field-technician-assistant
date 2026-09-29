# Testing

```sh
make test     # backend suite + agentctl suite (no key, ~10 s)
make e2e      # Playwright: demo flow, mobile layout, axe WCAG 2.1 AA, keyboard
make check    # test + TypeScript typecheck + secret scan + agentctl doctor
make smoke    # live provider from .env: 9 representative turns, PASS/FAIL only
make smoke-codex
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
| Adapters | `test_adapters.py`, `test_adapters_gemini.py`, `test_codex.py` | OpenAI/Anthropic/Gemini request and response shapes and error mapping; Gemini header auth and thought-signature replay; Codex sandbox argv, output parsing, and a full run through a fake `codex` binary |
| Agent tooling | `tools/tests/test_agentctl.py` | Claims across worktrees; overlap; deps; stale takeover; check-paths; adapters |
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

The original, more detailed specification of these scenarios is in [archive/acceptance-tests.md](archive/acceptance-tests.md).
