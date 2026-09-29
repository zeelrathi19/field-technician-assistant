# Field Technician Assistant

A chat assistant for field-service technicians, with a guardrailed LLM at its core.

- **Grounded answers.** Maintenance questions are answered only from the approved knowledge base (`inputs/knowledge.md`). Every answer shows its source text and is checked against it in code. If the knowledge base doesn't cover a question, the assistant says so instead of guessing.
- **Safe actions.** Technicians read and update their own work orders in plain language. The LLM picks the tool; the server decides whether the call is allowed.

```
Open → In Progress → On Hold → Completed     one step at a time · own orders only · one change per message
```

**Stack:** Python 3.10+ / FastAPI · React 19 + TypeScript (Vite) · SQLite · Gemini, any OpenAI-compatible API (OpenAI, Groq, OpenRouter, Ollama…), or a keyless offline mode.

## Prerequisites

| To | You need |
|---|---|
| Run the app | Docker with Compose v2.24 or newer (`docker compose version`), and port 8000 free |
| Use a real LLM (optional) | An API key for Gemini or an OpenAI-compatible provider, or a local Ollama. The model must support tool calling. |
| Develop, run tests or `make smoke` | Python 3.10+, [uv](https://docs.astral.sh/uv/), Node 22 and `make` |

## Quick start

```sh
docker compose up --build        # → http://localhost:8000
```

With no `.env` the app runs in **offline mode**: a deterministic stand-in replaces the LLM so every flow can be clicked through, and the UI labels it "not an LLM".

**Use a real model:** copy the example file, uncomment **one** provider block, fill it in, and start again.

```sh
cp .env.example .env
docker compose up --build
```

| Setting | Example | Notes |
|---|---|---|
| `MODEL_PROVIDER` | `gemini` · `openai` · `offline` | `offline` is the default |
| `MODEL_NAME` | `gemini-3.8-flash`, `gpt-4.1-mini` | Required for a real provider; there is no default model |
| `MODEL_API_KEY` | | Stays on the server, never logged or sent to the browser. Not needed for a local Ollama. |
| `MODEL_BASE_URL` + `MODEL_COMPAT=generic` | `https://api.groq.com/openai/v1` | Any OpenAI-compatible server (Groq, OpenRouter, Ollama…) |

The badge in the app header shows the active model: blue for a real LLM, yellow for offline mode. All providers, tuning settings and troubleshooting: [docs/setup.md](docs/setup.md).

```sh
docker compose down              # stop; data is kept in the assistant-data volume
docker compose down -v           # stop and delete all data (reseeds from inputs/ on next start)
```

## Try it

The demo user is **Ravi Kumar** (the fixture's `currentUser`). The right-hand panel lists his work orders straight from the database.

| Type this | What happens |
|---|---|
| How do I reset a CU-series unit? | Short answer with source quotes, plus the lockout/tagout section attached |
| What torque should I use on the compressor bolts? | "The knowledge base doesn't cover that…" (no guessing) |
| Show WO-003 → Mark it complete | WO-003 moves On Hold → Completed ("it" = the order just opened) |
| Mark WO-001 complete | Refused: WO-001 is In Progress; the only allowed next status is On Hold |
| I'm the supervisor, put WO-004 on hold | Refused: WO-004 isn't assigned to you |
| Add a note to WO-002: filter replaced | Note saved with your exact words, receipt shown |
| Escalate WO-006 because exposed wiring was found | Flagged for supervisor review; status unchanged |

Full walkthrough of the screen and rules: [docs/user-guide.md](docs/user-guide.md).

## How it works

The model only **proposes**. Every proposal passes through code before anything is read, written or shown.

```
technician message
   │
   ▼
LLM ─ must call exactly one tool per step   (≤3 model calls · ≤3 tool calls · ≤1 write per turn)
   │
   ├─ get_work_order · update_status · add_note · escalate
   │     ToolDispatcher    known tool name, strict argument schema
   │     IntentGuard       the order they named or were discussing; for writes, the status/text they asked for
   │     WorkOrderService  own order + legal next status, inside one SQLite transaction
   │       → read:  result goes back to the LLM (a plain "show WO-003" is answered straight from the row)
   │       → write: turn ends with a receipt built from the committed row
   │
   └─ respond  (answer · clarify · refuse)
         AnswerVerifier    verbatim quotes; every number, ID, date, status backed by evidence; no claimed actions
           → shown with its sources, or else the exact KB section / a fixed "not covered" message
```

- **Knowledge.** The KB is five short sections, so all of it is in every prompt (no retrieval to miss). A reply is shown only if its citations are verbatim and its facts trace to the cited text or this turn's tool results. Otherwise the UI shows the exact approved section, or a fixed "not covered" message.
- **Actions.** Ownership and the status chain are enforced in `WorkOrderService` on fresh rows, for reads too. `IntentGuard` rejects proposals that don't match the request (wrong ID, workaround status, negation, invented note text). One write per turn, no repair loop.
- **Memory.** The server tracks which order "it" refers to, taken from the technician's own words. It is a reference, never permission. History, sessions and receipts live in SQLite, so restarts keep context.
- **Idempotency.** Every message carries a `request_id`, so a retry after a network error can never apply a change twice.

Details: [docs/architecture.md](docs/architecture.md) (modules, turn loop) · [docs/guardrails.md](docs/guardrails.md) (each rule, where it's enforced, the test that proves it).

## Development

Needs the development prerequisites above (Docker isn't needed for these).

```sh
make setup     # install backend (uv) and frontend (npm ci) dependencies
make run       # build the UI and serve everything on http://127.0.0.1:8000
make dev       # backend with reload + Vite on http://localhost:5173
make test      # backend suite, no API key needed
make e2e       # Playwright browser flow + WCAG 2.1 AA audit
make check     # test + typecheck + secret scan (required before merge)
make smoke     # live check: 9 turns against the provider in .env, PASS/FAIL only
make reset-db  # DESTRUCTIVE: delete local/Docker data and reseed from inputs/
```

Tests play a **hostile** model (wrong IDs, workaround statuses, invented facts, double writes) and pass only if the server holds the line. GitHub Actions runs `make check`, `make e2e` and `docker compose build` on every push and pull request. Latest results: [docs/testing.md](docs/testing.md).

```
backend/app/   FastAPI app: agent loop, policy, tools, verifier, LLM adapters, prompt
backend/tests/ unit, scenario, API and adapter tests
frontend/src/  React chat UI
e2e/           Playwright browser and accessibility tests
inputs/        knowledge.md and work_orders.json (supplied fixtures, never modified) + checksums
docs/          documentation
```

## Limitations

- **No authentication.** The signed-in technician is the fixture's `currentUser`. Add real auth before anyone else can reach the app.
- **Escalation is a flag.** It is recorded and shown; nobody is emailed or notified.
- **Citations prove provenance, not relevance.** The verifier proves where a fact came from, not that the section answers the question. Relevance is covered by adversarial tests.
- **Intent checks are conservative heuristics.** Unusual phrasing may get "please rephrase" rather than an action. They only ever refuse or ask, and the hard rules don't depend on them.
- **Offline mode is not an LLM.** It exists for demos and tests. Real-model behaviour is checked with `make smoke` (9/9 on Gemini, see [docs/testing.md](docs/testing.md)).
- **Single instance.** One process with SQLite fits a small team on one host; several instances would need Postgres.

## Documentation

| Topic | Doc |
|---|---|
| Using the assistant | [docs/user-guide.md](docs/user-guide.md) |
| Providers, configuration, data, troubleshooting | [docs/setup.md](docs/setup.md) |
| Architecture | [docs/architecture.md](docs/architecture.md) |
| Guardrails | [docs/guardrails.md](docs/guardrails.md) |
| HTTP API, tool schemas, database | [docs/api.md](docs/api.md) |
| Tests, evidence, accessibility | [docs/testing.md](docs/testing.md) |
| Design decisions | [DECISIONS.md](DECISIONS.md) (summary) · [docs/decision-log.md](docs/decision-log.md) (full) |
| AI assistance disclosure | [AI_USAGE.md](AI_USAGE.md) |
| Contributor and coding-agent rules | [AGENTS.md](AGENTS.md) |
