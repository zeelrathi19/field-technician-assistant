---
id: T01
title: Domain policy, SQLite persistence, work-order service
status: done
priority: P0
owner: claude-opus
depends_on: []
paths: [backend/app/domain.py, backend/app/db.py, backend/app/service.py, backend/app/config.py, backend/tests/test_domain.py, backend/tests/test_service.py]
---

## Goal
Status machine, ownership on every call, BEGIN IMMEDIATE transactions, seed once.

## Acceptance
- [x] 16 status pairs
- [x] ownership on all tools
- [x] rollback + concurrency tests
- [x] `make check` passes
