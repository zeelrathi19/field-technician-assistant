---
id: T04
title: LLM adapters (OpenAI-compatible, Anthropic, offline, scripted)
status: done
priority: P0
owner: claude-opus
depends_on: [T02]
paths: [backend/app/llm/**, backend/tests/test_adapters.py]
---

## Goal
Provider-neutral ModelClient; wire-shape contract tests.

## Acceptance
- [x] tool_choice required / any
- [x] no parallel calls
- [x] error mapping
- [x] `make check` passes
