---
id: T10
title: Live-provider conformance run (OpenAI, Anthropic, Gemini, local)
status: todo
priority: P0
owner: 
depends_on: [T05]
paths: [backend/evals/**, docs/validation.md]
---

## Goal
Run `make smoke` per provider/model; add a golden eval set (grounding, abstention, tool choice, refusal) with a pass-rate report. Record model/date/result only.

## Acceptance
- [ ] results table in docs/validation.md
- [ ] no secrets or raw prompts stored
- [ ] `make check` passes
