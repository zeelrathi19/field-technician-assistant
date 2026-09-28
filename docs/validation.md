# Validation evidence

This page lists commands that were actually run and the results they produced. Nothing here is a planned result. Latest full run: 29 Sep 2026, after the review fixes (T15, T17–T20).

## Automated suites

| Check | Command | Result |
|---|---|---|
| Backend: domain, service, tools, knowledge, intent, grounding, 50+ scenarios, review regressions, API, adapters, Codex provider | `make test` (part 1) | **235 passed** |
| agentctl: claims across worktrees, overlap, deps, stale takeover, check-paths, adapters, CLAUDE.md import | `make test` (part 2) | **10 passed** |
| Browser: demo flow, reload persistence, mobile reflow, axe WCAG 2.1 AA (light, dark, mobile), keyboard | `make e2e` | **5 passed**, 0 axe violations |
| TypeScript typecheck + production build | `make typecheck`, `make build-ui` | pass |
| Secret scan of tracked files, plus a token-pattern scan of the full history | `make secrets`, `git log --all -p \| grep …` | clean / 0 matches |
| Workspace integrity | `agentctl doctor` | ok |
| Markdown links (excluding the archive) | link checker | 0 broken |

Environments: build sandbox (Linux x86-64, Python 3.11 and 3.10). The owner's machine (aarch64, Python 3.10.12) passed the earlier 206 + 9 suite.

## Continuous integration

GitHub Actions on the private repo `zeelrathi19/field-technician-assistant`, run 36476263349 (first push). It ran `make setup` → `make check` → Playwright install → `make e2e` → **`docker compose build`**, all green on a clean Ubuntu runner. Every later push re-runs the same job.

## Requirement coverage (R1–R11)

| Req | Evidence |
|---|---|
| R1 Python backend + React UI | `backend/app`, `frontend/src`; e2e |
| R2 grounded answers / abstain | R01, R02, R17, S08–S13b, verifier and review-policy tests |
| R3 LLM tool selection (4 tools) | Adapter contract tests (`tool_choice` required/any, Codex output schema); scenarios through the full loop |
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

1. **Live LLM behaviour.** No provider key or Codex CLI was available where the build ran. Adapters are verified against recorded request/response shapes, and the Codex adapter through a fake binary. Run `make smoke` (API key) or `make smoke-codex` (ChatGPT login) and record the result here with model and date. This is board task T10.
2. **`docker compose up` smoke on the owner's machine.** The image build is verified in CI; the container runtime health check has not been observed end to end.

## Known limits (by design)

- A citation proves where a fact came from, not that the section is relevant.
- Intent checks are heuristics, and ask for a restatement when unsure. The hard rules don't depend on them.
- The identity is the fixture user. Add real authentication (T13) before shared use.
