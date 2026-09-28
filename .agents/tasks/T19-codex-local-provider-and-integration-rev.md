---
id: T19
title: Codex local provider and integration review
status: done
priority: P2
owner: claude-opus
depends_on: []
paths: [backend/app/config.py, backend/app/llm/**, backend/tests/test_codex.py, backend/app/main.py, backend/scripts/**, tools/codex*, Makefile, .env.example, docs/**, README.md, DECISIONS.md, AGENTS.md, AI_USAGE.md, architecture-guide.html]
---

## Goal
Provide safe local Codex-backed testing without API credentials and integrate review

## Acceptance
- [x] tests added and `make check` passes
