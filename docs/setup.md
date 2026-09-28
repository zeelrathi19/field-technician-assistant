# Setup and operations

## Ways to run

| Mode | Command | Needs | Model |
|---|---|---|---|
| Docker (the submission path) | `docker compose up --build` → http://localhost:8000 | Docker | From `.env` (none = offline) |
| Local | `make setup && make run` → http://127.0.0.1:8000 | [uv](https://docs.astral.sh/uv/), Node 22 | From `.env` |
| Local with Codex login | `make setup && make run-codex` | the `codex` CLI, already signed in (`codex login`) | Your Codex default model |
| Development | `make dev` → http://localhost:5173 | uv, Node | Backend reloads on save; Vite serves the UI and proxies `/api` |

In every mode the backend serves the built UI and the API from **one origin**, so there is no CORS. The port is bound to `127.0.0.1` only.

## Choosing a model provider

Copy `.env.example` to `.env` and uncomment **one** block. Settings from the real environment override `.env`. Restart after changes.

| Provider | Settings | Notes |
|---|---|---|
| Offline (default) | `MODEL_PROVIDER=offline` | Deterministic rules, **not an LLM**. For demos, CI and e2e tests. |
| OpenAI | `MODEL_PROVIDER=openai`, `MODEL_NAME`, `MODEL_API_KEY` | Strict tool schemas, `tool_choice=required`, no parallel calls |
| Anthropic | `MODEL_PROVIDER=anthropic`, `MODEL_NAME`, `MODEL_API_KEY` | Native tool use, `tool_choice=any` |
| Gemini | `MODEL_PROVIDER=openai`, `MODEL_COMPAT=generic`, `MODEL_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/`, `MODEL_NAME`, `MODEL_API_KEY` | Uses Gemini's OpenAI-compatible endpoint |
| Groq / OpenRouter / Together / DeepSeek / Mistral | `MODEL_PROVIDER=openai`, `MODEL_COMPAT=generic`, `MODEL_BASE_URL=<their /v1 URL>`, `MODEL_NAME`, `MODEL_API_KEY` | `generic` drops parameters some servers reject |
| Ollama / vLLM / LM Studio | `MODEL_PROVIDER=openai`, `MODEL_COMPAT=generic`, `MODEL_BASE_URL=http://localhost:11434/v1` (from Docker: `http://host.docker.internal:11434/v1`), `MODEL_NAME` | No key needed for local URLs. Pick a model that supports tool calling. |
| Codex CLI | `MODEL_PROVIDER=codex` (optional `MODEL_NAME`, `CODEX_BIN`) | Uses your ChatGPT login, no API key. Each model step runs `codex exec` read-only in an empty temp folder. It is slow (tens of seconds per step), so `make run-codex` raises the timeouts. Not available inside Docker. |

Use a model name your account can access that supports tool calling. The app never guesses a default model name. Check a provider with `make smoke` (or `make smoke-codex`). It prints PASS/FAIL for nine representative turns, never keys or prompts.

## Configuration reference

All settings are environment variables, validated at startup. An invalid value stops the app with a clear error. The hard rules (ownership, status chain, one write per turn) are not configurable.

| Variable | Default | Meaning |
|---|---|---|
| `MODEL_PROVIDER` | `offline` | `openai` · `anthropic` · `codex` · `offline` |
| `MODEL_NAME` | — | Required for `openai`/`anthropic` |
| `MODEL_API_KEY` | — | Required for hosted `openai`/`anthropic`; never sent to the browser |
| `MODEL_BASE_URL` | — | OpenAI-compatible endpoint |
| `MODEL_COMPAT` | `openai` | `generic` for non-OpenAI servers |
| `MODEL_TEMPERATURE` | unset | Only sent if set (some reasoning models reject it) |
| `CODEX_BIN` | `codex` | Path to the Codex CLI |
| `MODEL_TIMEOUT_SECONDS` / `TURN_TIMEOUT_SECONDS` | 30 / 60 | Per model call / per whole turn (max 300 / 900) |
| `MAX_MODEL_CALLS_PER_TURN` / `MAX_TOOL_CALLS_PER_TURN` | 3 / 3 | Budgets; rejected calls count |
| `MAX_OUTPUT_TOKENS` | 1024 | |
| `MODEL_CONCURRENCY` | 4 | Concurrent model calls across all chats |
| `HISTORY_MESSAGES` / `HISTORY_CHAR_BUDGET` | 8 / 12000 | Conversation window sent to the model |
| `MAX_MESSAGE_CHARS` / `MAX_NOTE_CHARS` / `MAX_REASON_CHARS` | 8000 / 2000 / 500 | Input limits (the request body is also capped at 64 KB) |
| `DATABASE_PATH` | `data/assistant.sqlite3` (Docker: `/data/assistant.sqlite3`) | SQLite file |
| `KNOWLEDGE_PATH` / `WORK_ORDERS_PATH` / `FRONTEND_DIST` | `inputs/…`, `frontend/dist` | |
| `ALLOWED_ORIGINS` | localhost:8000, :5173 | Origins allowed to POST |
| `SECURE_COOKIES` | false | Set true behind HTTPS |
| `LOG_LEVEL` | INFO | JSON logs with metadata only; no message bodies |

## Data

- **First start:** the app seeds SQLite from `inputs/work_orders.json` and pins the file's hash. After that the database is the source of truth, and restarts keep your changes.
- **Changed fixture:** if `work_orders.json` changes after seeding, the app refuses to start rather than merge. Reseed deliberately with `make reset-db`, which deletes local and Docker data.
- **Where data lives:**
  - Docker: the `assistant-data` volume. `docker compose down` keeps it; `down -v` deletes it.
  - Local: `data/`, which git ignores.
- **Stored:** work orders, notes, escalations, chat sessions and messages, request receipts and an audit trail (no note bodies in the audit).

## Troubleshooting

| Symptom | Fix |
|---|---|
| Startup error mentioning `MODEL_NAME`/`MODEL_API_KEY` | Fill in the provider block in `.env`, or remove `.env` for offline mode |
| `MODEL_PROVIDER=codex but 'codex' is not on PATH` | Install the Codex CLI and run `codex login`, or set `CODEX_BIN` |
| "The work-order fixture changed after this database was seeded" | `make reset-db` (destructive) |
| Replies say "The model provider is unavailable" | Network, rate limit or a timeout. Press Retry; nothing was changed. |
| "…rejected the request (server configuration)" | Wrong key, model name or endpoint. Check the server logs (no secrets are logged). |
| Blank page at :8000 in local mode | Run `make build-ui` (`make run` does it for you) |
| e2e: "Executable doesn't exist" | `cd backend && uv run playwright install chromium`, or set `PLAYWRIGHT_CHROMIUM_EXECUTABLE` |

## Publishing

The repository is private on GitHub. If you ever need to push it somewhere new, `tools/publish-github.sh <owner> <repo>` creates a **private** repo and pushes `main`. It reads the token from `$GH_TOKEN` or a hidden prompt, and never writes it to disk, the remote URL or git config. Revoke single-use tokens afterwards.
