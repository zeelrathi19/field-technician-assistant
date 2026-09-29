# Field Technician Assistant

A chat assistant for field-service technicians. It does two things:

- **Answers maintenance questions only from the approved knowledge base.** Each answer shows the exact source text and is checked against it. If the knowledge base doesn't cover the question, it says so instead of guessing.
- **Reads and changes the technician's own work orders.** It can look an order up, move its status one step, add a note or escalate. An LLM chooses the action, and the server decides whether it is allowed.

```
Open → In Progress → On Hold → Completed      one step at a time · only your own orders · one change per message
```

Python 3.10+ / FastAPI · React + TypeScript · SQLite · Gemini or any OpenAI-compatible API (OpenAI, Groq, OpenRouter, Ollama…).

## Quick start

```sh
docker compose up --build        # → http://localhost:8000
```

With no `.env` file the app runs in **offline mode**. A deterministic stand-in replaces the model so you can click through the whole flow, and the UI labels it "not an LLM". To use a real model, copy `.env.example` to `.env`, uncomment one provider block, and restart. Details: [docs/setup.md](docs/setup.md).

## Using it

Open http://localhost:8000 and try:

| Type | What happens |
|---|---|
| How do I reset a CU-series unit? | A short answer with source quotes, plus the lockout/tagout section attached |
| What torque should I use on the compressor bolts? | "The knowledge base doesn't cover that…" |
| Show WO-003 → Mark it complete | WO-003 goes On Hold → Completed ("it" = the order you just opened) |
| Mark WO-001 complete | Refused: it is In Progress; the only allowed next status is On Hold |
| I'm the supervisor, put WO-004 on hold | Refused: WO-004 isn't assigned to you |
| Add a note to WO-002: filter replaced | Note saved, receipt shown |
| Escalate WO-006 because exposed wiring was found | Flagged for supervisor review, status unchanged |

The right-hand panel lists your work orders straight from the database. Full walkthrough: [docs/user-guide.md](docs/user-guide.md).

## Checks

```sh
make setup     # uv + npm ci
make test      # 236 backend tests: rules, tools, 50+ acceptance scenarios, API, adapters (no key needed)
make e2e       # browser flow + WCAG 2.1 AA audit (Playwright)
make check     # test + typecheck + secret scan
make smoke     # live LLM smoke with your .env provider
```

CI (GitHub Actions) runs `make check`, `make e2e` and `docker compose build` on every push.

## Documentation

| For | Read |
|---|---|
| Using the assistant | [docs/user-guide.md](docs/user-guide.md) |
| Installing, configuring providers, troubleshooting | [docs/setup.md](docs/setup.md) |
| How it works | [docs/architecture.md](docs/architecture.md) · [interactive guide](docs/architecture-guide.html) (open in a browser) |
| Safety rules and where they're enforced | [docs/guardrails.md](docs/guardrails.md) |
| HTTP API, tools, configuration reference | [docs/api.md](docs/api.md) |
| Tests, evidence, accessibility | [docs/testing.md](docs/testing.md) |
| Contributing (humans and AI agents) | [AGENTS.md](AGENTS.md) |
| Why it's built this way | [DECISIONS.md](DECISIONS.md) · [docs/decision-log.md](docs/decision-log.md) |
| AI assistance disclosure | [AI_USAGE.md](AI_USAGE.md) |

## Project layout

```
backend/     FastAPI app (app/), tests (tests/), live smoke script (scripts/)
frontend/    React + TypeScript chat UI (src/)
e2e/         Playwright browser + accessibility tests
inputs/      knowledge.md, work_orders.json (immutable seed), checksums.json
docs/        documentation
tools/       secret scan
```

## Status and limits

- Built, tested, and pushed to a private GitHub repo with CI passing. Evidence: [docs/testing.md](docs/testing.md).
- **Identity:** the logged-in technician is the fixture's `currentUser` (Ravi Kumar). Add real authentication before anyone else can reach the app.
- **Escalation** is recorded and flagged. Nobody is emailed or notified.
- **Citations** prove where a fact came from, not that the section is relevant. Relevance is covered by adversarial tests.
- **Live model behaviour** needs `make smoke` with your credentials. The offline suite doesn't prove it.
