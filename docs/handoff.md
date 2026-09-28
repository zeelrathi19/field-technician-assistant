# Handoff — current state (29 Sep 2026)

**State:** implemented. `main` has the backend, the UI, tests, Docker files and the agent workspace. `make check` and `make e2e` are green. Evidence is in `docs/validation.md`.

## For the next agent or human

1. Run `make context`, then pick a ready task (T10 live-provider conformance and T16 commit email are P0).
2. Before submitting the assessment:
   - put a provider in `.env` and run `make smoke`
   - run `docker compose up --build` on a machine that can reach Docker Hub
   - run `tools/set-git-email.sh <zeel's verified email>`
   - review `DECISIONS.md`.
3. Keep `ASSIGNMENT.pdf` out of git (it is ignored). If you have it, re-check `docs/EVALUATION.md` §1 against it. The PDF was not in the package this build used.

## Atomic project learnings

See `.agents/LEARNINGS.md` (append with `python3 tools/agentctl.py learn`).

## Report template

`python3 tools/agentctl.py handoff <TASK> --agent <name> --provider <llm> --summary ... --checks ... --risks ... --next ...` writes `.agents/handoffs/<date>-<task>-<agent>.md`.
