# Field technician assistant

**Implementation-ready plan — application code is not built yet.** Designed for Zeel Rathi from the supplied assessment, knowledge base, and work-order fixtures.

Start with [the offline HTML architecture guide](architecture-guide.html), then follow [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md). Implementing agents must read [AGENTS.md](AGENTS.md).

The design uses Python/FastAPI, a minimal React/TypeScript chat UI, SQLite, and a replaceable model adapter. The LLM proposes structured calls; backend code enforces ownership, the exact status sequence, argument validation, and bounded execution. Technical replies use cited knowledge-base excerpts. Session memory resolves references across turns.

## Read next

- [Short assessment answers](DECISIONS.md) and [complete decision log](docs/decision-log.md).
- [Tool/API contracts](docs/contracts.md), [memory and prompts](docs/memory-and-prompts.md), [guardrails](docs/guardrails.md).
- [Acceptance tests](docs/acceptance-tests.md) and [setup, git, logging, delivery](docs/delivery-and-workflow.md).

## Run target

After implementation and one-time `.env` setup with a provider API key and supported model:

```sh
docker compose up --build
```

This is the **planned launch command**; Compose/backend/frontend files are not part of this plan-only delivery. The eventual UI will be at `http://localhost:8000`. The HTML guide opens directly in a browser without installation or network access.

Never commit API keys or tokens. Keep `.env` ignored. The assignment PDF is omitted. Supplied fixture copies live in `inputs/`; use this package within the assessment workflow. No repository has been pushed. Set git author name to **Zeel Rathi** and obtain the user's verified email before committing.

See [AI_USAGE.md](AI_USAGE.md) for assistance and verification disclosure.
