# Validation evidence

Run 29 Sep 2026 in the build sandbox (Linux, Python 3.11.15, Node 22.22.2, uv, Chromium 1194).
These are the results the commands actually produced. Nothing below is a planned result.

| Check | Command | Result |
|---|---|---|
| Backend: domain, service, tools, KB, intent, grounding, scenarios, API, adapters | `make test` (part 1) | **206 passed** |
| agentctl (two agents, worktrees, overlap, stale takeover, pointer drift) | `make test` (part 2) | **9 passed** |
| Browser e2e: KB answer → show WO-003 → "mark it complete" → skip refused → foreign refused → firmware abstains → reload keeps history; 390 px has no horizontal scroll | `make e2e` (offline model) | **2 passed**, no page errors |
| TypeScript typecheck + production build | `make typecheck`, `make build-ui` | pass (234 kB JS, 8 kB CSS) |
| Secret / forbidden-file scan | `make secrets` | clean |
| Agent workspace integrity | `python3 tools/agentctl.py doctor` | ok (16 tasks, 7 pointer files in sync) |
| Compose file | `docker compose config -q` | valid |
| Container layout | `pip install --require-hashes -r backend/requirements.lock` into a fresh venv, then served the Dockerfile layout (`/app/backend`, `/app/inputs`, `/app/frontend/dist`) with the Dockerfile's env vars | `/api/health` ok, UI served, DB created in the data dir |
| Live-pipeline smoke script | `uv run python scripts/smoke.py --allow-offline` | 9/9 (offline model; validates the script, **not** an LLM) |
| HTML guide | Playwright: clicked all 7 scenarios at 1280 px and 390 px | no JS errors, no horizontal overflow; 20 unique ids; all internal/local links resolve |
| Fixture integrity | `sha256sum inputs/*` vs `docs/source-manifest.json` | identical |
| Same suite on the user's machine (Linux VM, aarch64, Python 3.10.12, fresh `uv sync`) | `uv run pytest` + `pytest ../tools/tests` | **206 passed**, **9 passed** |
| Email-rewrite script | `tools/set-git-email.sh` on a throwaway clone | 13 commits rewritten, merges preserved |

## Requirement coverage (R1–R11)

| Req | Evidence |
|---|---|
| R1 Python backend + React UI | `backend/app`, `frontend/src`; e2e |
| R2 grounded / abstain | R01, R02, R17, S08–S13b, `test_verifier_*`, `test_evidence_free_domain_answer_abstains` |
| R3 LLM tool selection (4 tools) | Adapter wire tests (`tool_choice` required/any), scenario tests through the full loop |
| R4 ownership | `test_service.py` (all tools × foreign IDs), R09, R10, S01, S25 |
| R5 status chain | 16-pair test, R04–R08, S05, S06, C08 |
| R6 unknown / malformed | `test_tools.py`, R11, R12, S21 |
| R7 context across turns | R13, R14, S02–S04, S14, S15, clarification tests |
| R8 DECISIONS.md | root file: the three answers |
| R9 repo with backend + frontend | this repository |
| R10 one command, README, key in env | `docker compose up --build` (config validated; see gap), README, `.env.example` |
| R11 AI disclosure | `AI_USAGE.md` |

## Not verified here (open)

1. **`docker compose up --build` end to end.** The sandbox's egress policy blocks Docker Hub (`registry-1.docker.io` → 403), so base images cannot be pulled. The same layout was reproduced and served without Docker. Run it once on a normal machine (tracked as a CI job in `.github/workflows/ci.yml`).
2. **Live LLM behaviour.** No provider key was available. Adapters are verified against recorded OpenAI/Anthropic request and response shapes, including error mapping. Run `make smoke` with a key to verify live behaviour. Board task T10 adds a multi-provider eval.
3. ~~Commit email~~ — resolved: history rewritten to Zeel's verified address before the first push (T16).

## Known limits (by design)

- The verifier proves where a fact came from, not that the section is relevant.
- Status-name claims are checked against all evidence in the turn, including the roster, not per order. The work-order card shown next to the answer is the authoritative view.
- The intent checks are heuristics, and on odd phrasing they ask for a restatement. The hard rules (ownership, the adjacent status chain, the schemas and one write per turn) do not depend on them.
