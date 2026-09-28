# Learnings (append-only; `python3 tools/agentctl.py learn ...`)

Format: `- date [agent] observation — evidence: ... — consequence: ...` (mark untested ideas `(hypothesis)`).

- 2026-09-29 [claude-opus] Status chain contains a mandatory On Hold between In Progress and Completed — evidence: plan R5 / assignment page 2 — consequence: WO-001 "complete" must be refused, never walked through On Hold.
- 2026-09-29 [claude-opus] WO-008 mentions firmware but the KB has no firmware procedure — evidence: inputs/work_orders.json vs inputs/knowledge.md — consequence: work-order steps are never evidence; S09 test pins abstention.
- 2026-09-29 [claude-opus] anthropic>=1.x SDK uses `httpx2`, openai SDK uses `httpx` — evidence: TypeError when injecting httpx.Client — consequence: adapter tests build transports per SDK.
- 2026-09-29 [claude-opus] A regex command grammar made the LLM decorative; consistency checks keep safety with natural phrasing — evidence: tests `test_natural_phrasing_accepted`, S05, C01 — consequence: IntentGuard checks binding/status words/payload grounding instead of parsing commands.
- 2026-09-29 [claude-opus] Docker Hub is blocked from the build sandbox — evidence: 403 on registry-1.docker.io — consequence: image layout was reproduced without Docker; run `docker compose up --build` on a machine with registry access.
