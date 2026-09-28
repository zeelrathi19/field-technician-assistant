---
id: T19
title: Codex local provider and integration review
status: todo
priority: P2
owner:
depends_on: []
paths: [backend/app/config.py, backend/app/llm/**, backend/tests/test_codex.py, backend/app/main.py, backend/scripts/**, tools/codex*, Makefile, .env.example, docs/**, README.md, DECISIONS.md, AGENTS.md, AI_USAGE.md, architecture-guide.html]
---

## Goal
Provide safe local Codex-backed testing without API credentials and integrate review

## Acceptance
- [ ] tests added and `make check` passes
