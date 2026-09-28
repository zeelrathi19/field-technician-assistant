---
id: T11
title: Native Gemini adapter (google-genai)
status: todo
priority: P2
owner: 
depends_on: [T04]
paths: [backend/app/llm/gemini_native.py, backend/app/llm/factory.py, backend/tests/test_adapters_gemini.py]
---

## Goal
Optional native adapter (function calling mode ANY) alongside the OpenAI-compatible path.

## Acceptance
- [ ] wire-shape tests
- [ ] factory branch + Settings literal
- [ ] `make check` passes
