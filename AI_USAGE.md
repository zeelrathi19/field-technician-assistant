# AI assistance disclosure

**Planning (28 Sep 2026).** Codex read the assignment and fixtures and produced the planning package: the plan, contracts, guardrails, acceptance list and HTML guide. Three Codex subagents drafted parts of it, and an integrating agent reconciled them.

**Implementation (29 Sep 2026).** Claude (Anthropic, Cowork) did the following:

- evaluated the plan against the fixtures (`docs/EVALUATION.md`)
- changed three design points: consistency checks instead of a regex command grammar, verified quoting instead of verbatim-only answers, and a multi-provider model layer
- wrote the backend, UI, tests, Docker files, agent-coordination tooling and documentation.

Commits are authored as Zeel Rathi, with Claude as co-author in the commit trailers.

**Verification actually performed.** The exact commands and results are in `docs/validation.md`. Summary:

- Automated suite: unit, scenario, API, adapter wire-shape and agentctl tests.
- Playwright browser e2e against the running app.
- Frontend typecheck and build.
- Secret scan.
- A reproduction of the container layout, installed from the hash-locked requirements and served.

**Not verified here:**

- **`docker compose build`:** the build sandbox cannot reach Docker Hub.
- **Live LLM behaviour:** no provider key was available. The adapters were checked against recorded request/response shapes only. Run `make smoke` with a key to verify live behaviour.

The offline heuristic model is a test double, not evidence of LLM quality.

Human review is still expected before submission. In particular, read `DECISIONS.md`, and confirm the commit email (`tools/set-git-email.sh`).
