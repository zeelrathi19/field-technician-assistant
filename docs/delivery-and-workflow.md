# Delivery and development workflow

> **Status (29 Sep 2026): implemented.** `compose.yaml`, `Dockerfile`, `Makefile`, lockfiles (`backend/uv.lock`, `backend/requirements.lock`, `frontend/package-lock.json`) exist. Differences: without `.env` the app starts in labelled offline mode instead of failing; parallel-agent workflow is now tooled by `tools/agentctl.py` (see AGENTS.md).

This is an implementation specification. Commands, runtime files, and verification gates below describe what the implementer must create and prove; they do not claim that the application already exists or passes checks. Read the architecture and implementation plan before starting. Record material choices in the decision record, using a short rationale, alternatives considered, and consequence. Do not record private reasoning transcripts.

## Scope and operating assumptions

Build a small Python API with a minimal React TypeScript message list and input. Use one application process, a local SQLite database, and the supplied knowledge and work-order fixtures. Avoid Redis, a vector database, a task queue, Kubernetes, microservices, and multiple model agents. These additions do not solve a demonstrated requirement for this assessment.

Treat `currentUser` from the supplied fixture as the authenticated identity for this local assessment. Resolve it in trusted server code; never accept a technician identity from a chat message, tool argument, or browser request. Real deployment requires authentication and a server-verified principal before exposing the application to other users. A browser session identifier alone is not authentication.

Keep the supplied assignment PDF outside the repository. It is confidential assessment input, not an application asset. Do not reproduce the assignment in a public repository. Keep the working repository and any remote private unless the user establishes permission to publish; review the supplied knowledge and work-order data for redistribution permission too. Use synthetic examples in public demonstrations.

## Environment and configuration

Use Python 3.12 and Node.js 22 as initial implementation targets. Pin exact compatible package versions through lockfiles after installation; verify supported versions when implementing instead of relying on these targets indefinitely. Use FastAPI, Pydantic settings, the selected provider SDK, SQLite, React, TypeScript, and Vite. Prefer the Python standard library where it already supplies a clear solution. Use classes at stable boundaries—model adapter, tool dispatcher, work-order service, repository—not a class for every function.

The repository must include:

| File | Purpose |
| --- | --- |
| `backend/pyproject.toml` and Python lockfile | Runtime and development dependencies; reproducible installation |
| `frontend/package.json` and `package-lock.json` | UI scripts and reproducible npm installation |
| `.env.example` | Documented, non-secret values and an empty API-key field |
| `.gitignore` and `.dockerignore` | Exclude secrets, local data, build artifacts, caches, and confidential source PDF |
| `compose.yaml` and Dockerfiles | One-command launcher and health checks |
| `README.md` | Short setup, operation, checks, limitations, and links to detailed documents |

Load configuration once at startup into a validated settings object. Do not scatter environment reads across business logic. Keep the concrete backend layout consistent with the architecture document.

| Setting | Contract |
| --- | --- |
| `MODEL_PROVIDER` | Allowlisted adapter identifier; fail startup on unsupported values |
| `MODEL_NAME` | Explicit provider model identifier; avoid mutable defaults hidden in code |
| `MODEL_API_KEY` | Required server-only secret for the selected live provider; never pass it to React |
| `DATABASE_PATH` | Writable runtime database path, distinct from source fixtures |
| `KNOWLEDGE_PATH` / `WORK_ORDERS_PATH` | Readable fixture paths; validate expected content at startup |
| `LOG_LEVEL` | Validated log level; default `INFO` |
| `MODEL_TIMEOUT_SECONDS` | Finite positive timeout; initial target 30 seconds |
| `MAX_MODEL_CALLS_PER_TURN` | Finite positive loop limit; initial target 2 total attempts, including retries |
| `MAX_TOOL_CALLS_PER_TURN` | Finite positive execution limit; initial target 2 |
| `MODEL_CONTEXT_TOKENS` | Configured context capacity, checked against adapter capabilities |
| `MAX_OUTPUT_TOKENS` | Reserved output budget; initial target 1024 |

The canonical defaults and hard execution ceilings are in `docs/contracts.md`. Timeout and capacity settings are operational values; the one-mutation invariant cannot be configured off. Changes to call ceilings require a reviewed contract and test update. Context management must reserve room for the immutable system policy, selected knowledge, current state, proposed tool arguments, tool results, and output before including conversational history. If the model context cannot fit mandatory material, fail safely or request a narrower question. Never silently drop the policy or a pending action to make room.

Validate missing key, missing fixture, unsupported provider, invalid limits, unreadable database, and malformed seed data at startup. Return a useful operator error without printing secrets. An optional deterministic fake adapter is for automated tests only and must never be represented as a working live assistant.

## One-command runtime contract

The implementer must provide this documented path:

```sh
cp .env.example .env
# Set MODEL_PROVIDER, MODEL_NAME, and MODEL_API_KEY in .env.
docker compose up --build
```

Configuration is a one-time prerequisite; the final line is the one-command launcher. Bind the browser endpoint to localhost for the assessment. Use one Compose app service: a multi-stage Docker build compiles React, then FastAPI serves its static output and `/api` at `http://localhost:8000`, avoiding a broad CORS allowlist. Only development uses a Vite `/api` proxy. Keep backend credentials on the server. Persist SQLite on a named volume or an explicitly ignored runtime directory. Seed an empty database once; restarting must preserve actions and conversation state rather than reseeding over them.

Compose must define an app readiness health check without secrets, and permit a clean `docker compose down` without deleting data. Document volume deletion as a separate, explicitly destructive reset operation. Do not silently reset data in a launcher or migration. Verify the launcher from a clean checkout with the README instructions and a real configured model before claiming it works.

Provide a development path too: isolated Python environment plus locked backend install, `npm ci` for the frontend, and documented backend/frontend dev commands. Docker remains the submission's primary run path. Do not require the evaluator to install a global Python package or npm package.

## Data, state, and logs

Treat the JSON fixture as immutable seed input. Store work orders, notes, escalations, conversation messages, explicit conversation state, and action outcomes in SQLite. Use parameterized queries, transactions, schema versioning, and foreign keys. Serialize changes to a work order and validate its current status inside the transaction; a stale model prediction must not bypass the current database state. SQLite is sufficient for a small single-service deployment; move to PostgreSQL only when measured concurrent-write pressure or deployment topology requires it.

Each conversation belongs to the server-verified user. Every read and write must check that relationship, including history retrieval. The work-order service must independently check ownership on every tool invocation. Do not trust a remembered work-order ID as authorization. Keep structured state such as `active_work_order_id` separate from the transcript; update it only from validated, authorized tool results. Preserve assistant/tool message pairing when trimming context.

Use a request identifier, conversation identifier, tool identifier, elapsed time, outcome category, policy-rejection code, and provider token usage when available as structured telemetry. Keep raw user messages, note text, escalation reasons, full work-order payloads, retrieved passages, authorization headers, and API keys out of default logs. Do not treat a verbose provider SDK trace as acceptable default logging. Store necessary application content in the database, where it can be deleted deliberately, rather than duplicating it in logs.

Maintain an action audit record with the actor, work-order ID, operation, before/after status when applicable, timestamp, and idempotency key. Do not copy note text into this operational audit merely for convenience. Commit the state change and its audit outcome atomically. An action reported as successful must have a committed outcome. Persist completed tool outcomes so a provider timeout or repeated model call cannot create duplicate notes or escalations. If execution has an uncertain result, reconcile by action ID before retrying.

For the local assessment, retain database state until explicit reset, document where it is stored, and use bounded rotating operational logs. Before broader deployment, define retention periods and deletion semantics appropriate to the actual customer and jurisdiction. Do not claim regulatory compliance from this plan alone. Backups, database exports, transcripts, and screenshots may contain customer data and must stay out of Git.

## Git, branches, and pull requests

All project commits must use the author name **Zeel Rathi**. The user's email is not supplied. Before the first commit, obtain or verify an email the user authorizes; never invent one or copy an unrelated global identity. Configure identity locally for this repository, then inspect it before committing:

```sh
git config --local user.name "Zeel Rathi"
# Set user.email to the user's verified, authorized address.
git config --get user.name
git config --get user.email
```

Do not change the user's global Git configuration. Do not create commits or push a remote solely because these instructions exist. The current scope prepares the work; remote URL, access method, and push timing must follow the user's actual instructions.

Use `main` as the reviewed integration branch. Create focused branches such as `feature/backend-domain`, `feature/tool-dispatch`, `feature/chat-ui`, `fix/status-validation`, or `docs/operator-guide`. Branch from a current reviewed base, implement a cohesive change, and open a pull request; do not develop modules or features directly on `main`. A separate production branch is unnecessary until a deployment workflow requires one. Set branch protection on the remote when available.

Use short imperative commit subjects that explain the change. Keep formatting-only changes separate from behavior changes. A pull request must state the problem, final behavior, validation actually run, material limitations, and any migration or configuration change. Link the applicable acceptance criteria and explain a security-relevant tradeoff when one exists. Require passing backend checks, frontend type/build checks, and the relevant behavioral tests before merge. Do not use successful CI as a substitute for reading the diff.

Before any commit or publication, review `git diff --cached`, inspect ignored files, and scan for credentials and confidential material. Store credentials through the user's approved credential manager or normal interactive authentication. Never embed tokens in remote URLs, scripts, documentation, commits, screenshots, or tool output. If a token is pasted into chat, treat it as exposed and use a replacement through a secure credential path. Authenticate only when remote publication is authorized. Never force-push or rewrite shared history as a routine cleanup step.

## Tool and dependency discipline

- **Python/FastAPI:** Typed API models and explicit error responses; keep transport, orchestration, domain policy, and persistence separate. Let the domain service own authorization and transitions. Avoid broad `except Exception` handlers that turn rejected actions into apparent success.
- **Provider SDK:** Access it only through the model adapter. Normalize text, tool calls, token usage, finish reason, and errors. Set timeouts; retry only transient failures within the turn budget. Do not automatically retry a mutation without a durable idempotency outcome.
- **React/TypeScript:** Display messages and pending/error states clearly; disable duplicate submissions during a turn. Render content as text or safely sanitized Markdown. Do not use raw HTML from the model. Show recoverable network failure without claiming an action failed or succeeded until the server confirms its outcome.
- **SQLite:** Use one explicit repository boundary, transactions, and a bounded busy timeout. Do not write the fixture JSON as a mutable datastore or let the model generate SQL.
- **Docker/npm/Python package tools:** Use lockfiles and minimal images; install only project dependencies. Keep secrets out of image layers. Verify dependency compatibility rather than adding frameworks speculatively.
- **Git:** Review small diffs, use focused branches and pull requests, preserve the requested author identity, and keep publication separate from local implementation.
- **AI development tools:** Record which tools assisted implementation and what human or automated verification was performed. Do not claim a test, scenario, review, or send occurred when it did not.

## Parallel implementation and handoff

Parallelize bounded work after agreeing on request/response schemas, state names, tool contracts, error codes, file ownership, and acceptance criteria. Suitable independent work is backend domain policy and persistence, the minimal UI against the agreed API contract, and documentation/test scenarios. Have one integration owner for orchestration and shared configuration. Do not let two agents edit the same file concurrently without a coordinated handoff.

Every agent must read the shared architecture and hard-rule invariants first. A handoff records files changed, contract changes, checks run with results, unresolved issues, and the next concrete action. An atomic learning states one observation, its evidence, and its consequence; a speculative idea is labelled as such. Record durable project learnings inside project documentation, not in a personal memory store without the user's explicit request.

## Deliverable gates

| Deliverable | Evidence required before marking complete |
| --- | --- |
| Backend | Real model chooses structured tool calls; registry rejects unknown tools and invalid arguments; application code rejects unauthorized and illegal transitions |
| Knowledge answers | Covered questions include traceable knowledge references; uncovered questions abstain; unrelated or malicious retrieved instructions cannot authorize actions |
| Conversation memory | Multi-turn scenario resolves a prior authorized work order; new and conflicting references behave predictably; separate sessions cannot read each other's state |
| React UI | Message list, input, pending state, recoverable errors, and end-to-end interaction with the real API work in a browser |
| Persistence | Restart preserves work-order changes and intended session state; duplicate action delivery does not duplicate side effects |
| Run instructions | Fresh-checkout setup and `docker compose up --build` succeed with an external API key; README accurately lists prerequisites |
| Decision record | Short `DECISIONS.md` answers all assignment questions and distinguishes implemented behavior from planned behavior |
| Tests | Ownership, exact status flow, malformed/unknown calls, prompt injection, missing evidence, context reference, idempotency, and provider failure checks pass |
| Repository or zip | Complete backend/frontend source, lockfiles, configuration example, launcher, tests, README, decisions, and explanation artifacts; no secrets or confidential PDF |
| Explanation artifact | Local HTML explains request flow, architecture, state, tools, guardrails, memory, setup, and tradeoffs; diagrams agree with actual implementation |

The README should be a short entry point: purpose; prerequisites and startup; key environment settings; tests; a compact architecture description; known limitations; and links to the deeper documents and HTML. Avoid copying the full plan into it. Keep a plan-only package clearly labelled until the runnable backend, frontend, and verification evidence exist.
