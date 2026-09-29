# AI assistance disclosure

| When | Tool | What it did |
|---|---|---|
| 28 Sep 2026 | Codex (with subagents) | Read the assignment and fixtures. Wrote the pre-build planning package: plan, contracts, guardrails, acceptance list, HTML guide (all later removed; the decisions carried over into `docs/decision-log.md`). |
| 29 Sep 2026 | Claude (Anthropic, Cowork) | Evaluated the plan. Built the backend, UI, tests, Docker files and agent-coordination tooling. Published to a private GitHub repo. |
| 29 Sep 2026 | Codex agents | Opened four review tasks (T15, T17–T19) on the shared board, then stopped before making changes. |
| 29 Sep 2026 | Claude | Took over those tasks: found and fixed seven guardrail/runtime flaws with regression tests (D53–D56), ran a WCAG 2.1 AA audit, added the native Gemini adapter (D59) and rewrote the docs. |
| 29 Sep 2026 | Claude (Cowork) | Cut to essentials (D60): removed the multi-agent tooling, archived plan, and Anthropic/Codex adapters; merged docs; re-ran the suites. |
| 29 Sep 2026 | Claude (Cowork) | Live Gemini fixes found during `make smoke` (D61–D63); submission cleanup of the docs (D64). |

Three design points differ from the plan: consistency checks instead of a command grammar, verified quoting instead of verbatim-only answers, and a multi-provider model layer. They are explained in `docs/decision-log.md`.

Commits are authored as Zeel Rathi. AI co-authorship is recorded in commit trailers.

**Verification actually performed** (details in `docs/testing.md`):
- the automated suites;
- Playwright e2e with an axe accessibility audit;
- TypeScript typecheck and build;
- a secret scan of the tracked files;
- a green GitHub Actions run, including `docker compose build`;
- a live `make smoke` on Gemini (`gemini-3.8-flash`, 9/9), run on the owner's machine.

The offline heuristic model is a test double, not evidence of LLM quality; live behaviour rests on the smoke run above.

Human review is still expected before submission, especially of `DECISIONS.md`.
