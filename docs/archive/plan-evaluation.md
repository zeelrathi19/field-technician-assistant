# Evaluation of the planning package (29 Sep 2026)

Reviewer: implementing agent, before build. Inputs reviewed: every file in the plan zip, `inputs/work_orders.json`, `inputs/knowledge.md`. **The assignment PDF was not in the zip** (the plan deliberately omitted it); requirements below are taken from the plan's own PDF mapping (R1–R11, page references in `docs/references.md`). If the PDF is later placed in the repo root as `ASSIGNMENT.pdf` (gitignored), re-check the table in §1.

## 1. What the assignment asks (as mapped by the plan)

| ID | Requirement | Plan verdict | Build decision |
|---|---|---|---|
| R1 | Python backend + minimal React UI | Correct | FastAPI + React/TS/Vite, one origin |
| R2 | Answer only from `knowledge.md`; say "don't know" otherwise | Correct but UX-hostile (verbatim whole sections only) | **Verified quoting**: short model answer + verbatim quotes, checked in code; falls back to whole sections |
| R3 | LLM selects structured tool calls (4 tools) | Correct | Native tool calling, `tool_choice=required`, plus a non-business `respond` channel |
| R4 | Act only on the current technician's work orders | Correct | Service-layer check on every tool incl. reads |
| R5 | Open → In Progress → On Hold → Completed, no skipping | Correct | Pure transition table, checked inside `BEGIN IMMEDIATE` |
| R6 | Reject unknown tools / malformed args | Correct | Static registry, strict Pydantic, duplicate-key/NaN/size rejection |
| R7 | Context across turns ("mark it complete") | Correct | Server-owned focus, resolved deterministically from the user's text |
| R8 | Short DECISIONS.md, three questions | Correct | Rewritten in past tense with real evidence |
| R9 | Repo or zip with backend + frontend | Missing (plan only) | Built |
| R10 | One-command launch, README, key via env | Missing | `docker compose up --build` verified; `make run` without Docker |
| R11 | Disclose AI assistance | Present for planning | Updated for the build |

## 2. What the fixtures actually exercise

- `currentUser = tech-ravi`. Ravi owns WO-001/002/003/005/006/008/010; Priya owns WO-004/009; Arjun owns WO-007.
- Positive transitions available on seed data: WO-002/WO-008 `Open→In Progress`, WO-001/WO-006 `In Progress→On Hold`, WO-003/WO-010 `On Hold→Completed`.
- Built-in traps: WO-001 "complete" (skip), WO-005 already Completed (terminal), WO-004 is Priya's *warranty dispute* (ownership + tempting KB §3/§4 match), WO-009 is Priya's hazard (tempting escalation), WO-008 mentions firmware (no KB coverage — must abstain), WO-001 mentions refrigerant pressure (no KB value), WO-006 exposed wiring (legit escalation per KB §4).
- All due dates are in July 2026, i.e. overdue relative to today; nothing in the spec asks the assistant to reason about that, so it is displayed but never inferred upon.
- KB is 5 sections / 2.4 KB → whole corpus fits every prompt; retrieval infrastructure would be waste.

## 3. Strengths of the plan (kept)

1. Correct trust boundary: model proposes, code authorizes, DB is truth, renderer reports receipts.
2. Ownership + status enforced in the service, not the prompt; unowned reads denied with a single public error.
3. Deterministic receipts for mutations; model never narrates success.
4. Idempotent request IDs, atomic check-and-write, one mutation per turn, no repair loop.
5. Focus stored outside chat history; foreign/missing ID clears focus (WO-003 → WO-004 → "it" must not touch WO-003).
6. Good adversarial test inventory (R01–R17, S01–S25, C01–C10).

## 4. Problems found and what the build changes

| # | Problem in plan | Risk | Change |
|---|---|---|---|
| E1 | No code at all; ~150 KB of docs for a 2–3 h assignment | Fails R9/R10 outright; reviewer fatigue | Build the app; keep docs, mark each as implemented/verified |
| E2 | **Anchored regex grammar (IntentGuard) required for every mutation** ("mark it complete" works, "WO-003 is done, close it out" does not) | The LLM becomes decorative; reviewers asked for LLM tool selection | LLM chooses tool + args. Code runs a *consistency* check instead of a grammar: target must be the explicit ID or current focus; requested status must be implied by the user's words (or "next"/"advance" = the one legal next status); negated/hypothetical phrasing blocks writes; note/reason must be grounded in the user's own words |
| E3 | Answers are whole verbatim KB sections only | "How long is labor covered?" returns the full warranty section; poor UX | Model writes ≤1200-char answer + verbatim quotes. Code verifies quotes are substrings of cited sections and every number/ID/status/date in the answer exists in the evidence. Any failure → deterministic fallback to full sections or abstention |
| E4 | Final structured answer "alongside tools" is provider-specific (OpenAI response_format + tools; Anthropic differs) | Adapter divergence | One non-executable `respond` tool + `tool_choice=required` works identically on OpenAI, Anthropic, Gemini (OpenAI endpoint), Groq, OpenRouter, Ollama |
| E5 | Only one provider, "fake adapter for tests only" | No way to demo/verify without a paid key; user wants multi-provider | Adapters: `openai` (any OpenAI-compatible base URL) and `anthropic`; `offline` deterministic heuristic model clearly labelled *not an LLM* for tests/e2e/keyless demo |
| E6 | "Exactly 4 tools" but no way to answer "what's on my plate?" | Common first question fails | Server injects a compact roster of the technician's own orders (id/title/status/due) as data; no fifth business tool; UI shows the roster panel from a non-LLM endpoint |
| E7 | Two-model-call cap | Read-then-answer-then-nothing is fine, but read → act needs 2 calls + the respond call | 3 model calls / 3 tool calls per turn, still exactly ≤1 mutation; a mutation ends the turn with a receipt |
| E8 | `MODEL_CONTEXT_TOKENS` required, no default | Extra operator friction for no benefit at 2.5 KB KB | Optional; history window is message-count + byte budget |
| E9 | CSRF/Origin/cookie + receipts endpoint + interrupted-request recovery all mandatory | Over-scoped for assessment | Kept, but minimal: HttpOnly browser cookie scopes sessions; Origin check on POST; idempotency table with interrupted marking at startup |
| E10 | "Parallel subagents" only as prose | Not usable by other agents/providers | Agent-agnostic workspace: canonical `AGENTS.md`, pointer files for every major agent, `tools/agentctl.py` (atomic claims shared across worktrees, path-overlap checks, handoffs, context dump), task board in `.agents/` |
| E11 | Git identity requires a verified email that was never supplied | Blocks commits | Commits use `Zeel Rathi <zeel.rathi@placeholder.invalid>`; `tools/set-git-email.sh` rewrites author/committer once the real email is known (done before first push) |
| E12 | HTML guide describes a plan with "not implemented" banners | Misleading after build | Guide updated to the implemented design |

## 5. Things deliberately *not* changed

- Status chain implemented literally (mandatory On Hold before Completed).
- Same-state requests are refused (not treated as no-ops); retries with the same request ID replay.
- Notes/escalations allowed on Completed orders (spec only constrains status).
- Escalation = stored flag + event; nothing is emailed.
- No vector DB, no summarizer, no multi-agent runtime.

## 6. Residual risks (honest)

- Status-keyword consistency and payload grounding are heuristics; the *hard* invariants (ownership, adjacency, schema, one write) do not depend on them.
- Relevance of a cited section is still model judgement; the verifier proves provenance, not relevance.
- Live-provider behaviour must be smoke-tested with a real key (`make smoke`); the suite uses scripted/offline models and recorded wire shapes.
