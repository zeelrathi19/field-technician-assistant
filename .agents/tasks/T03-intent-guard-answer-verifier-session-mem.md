---
id: T03
title: Intent guard, answer verifier, session memory, prompts
status: done
priority: P0
owner: claude-opus
depends_on: [T02]
paths: [backend/app/intent.py, backend/app/grounding.py, backend/app/memory.py, backend/app/prompts/**, backend/tests/test_intent.py, backend/tests/test_grounding.py]
---

## Goal
Consistency checks instead of a command grammar; provenance-verified answers; focus from user text.

## Acceptance
- [x] negation/hypothetical block writes
- [x] number words caught
- [x] `make check` passes
