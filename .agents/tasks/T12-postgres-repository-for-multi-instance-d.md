---
id: T12
title: Postgres repository for multi-instance deployment
status: todo
priority: P3
owner: 
depends_on: [T05]
paths: [backend/app/db.py, backend/app/service.py, compose.yaml]
---

## Goal
Only when measured contention or multiple instances require it. SELECT ... FOR UPDATE replaces BEGIN IMMEDIATE.

## Acceptance
- [ ] same service tests pass on Postgres
- [ ] `make check` passes
