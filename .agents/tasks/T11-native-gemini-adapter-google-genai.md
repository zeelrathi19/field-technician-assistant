---
id: T11
title: Native Gemini adapter (AI Studio AQ. keys)
status: done
priority: P2
owner: claude-opus
depends_on: [T04]
paths: [backend/app/llm/gemini_native.py, backend/app/llm/factory.py, backend/app/llm/errors.py, backend/app/llm/openai_compat.py, backend/app/llm/anthropic_native.py, backend/app/config.py, backend/scripts/**, backend/tests/test_adapters_gemini.py, .env.example, .gitignore, docs/**, README.md]
---

## Goal
Optional native adapter (function calling mode ANY) alongside the OpenAI-compatible path.

## Acceptance
- [x] wire-shape tests
- [x] factory branch + Settings literal
- [x] `make check` passes
