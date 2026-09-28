---
id: T05
title: ChatService turn loop and HTTP API
status: done
priority: P0
owner: claude-opus
depends_on: [T03, T04]
paths: [backend/app/agent.py, backend/app/api.py, backend/app/main.py, backend/app/logging_setup.py, backend/tests/test_scenarios.py, backend/tests/test_api.py, backend/tests/harness.py, backend/scripts/**]
---

## Goal
Bounded loop, idempotency, receipts, cookie-scoped sessions.

## Acceptance
- [x] R01-R17, S01-S25, C01-C09 pass
- [x] `make check` passes
