---
id: T02
title: Strict tool registry and knowledge base
status: done
priority: P0
owner: claude-opus
depends_on: [T01]
paths: [backend/app/tools.py, backend/app/knowledge.py, backend/tests/test_tools.py, backend/tests/test_knowledge.py]
---

## Goal
Five-tool registry with strict Pydantic; kb-1..kb-5 with verbatim-quote matching.

## Acceptance
- [x] malformed/unknown calls rejected
- [x] schemas match validators
- [x] `make check` passes
