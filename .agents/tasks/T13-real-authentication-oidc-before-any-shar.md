---
id: T13
title: Real authentication (OIDC) before any shared deployment
status: todo
priority: P1
owner: 
depends_on: [T05]
paths: [backend/app/api.py, backend/app/auth.py, frontend/src/api.ts]
---

## Goal
Replace the fixture principal with a verified identity; keep ownership checks unchanged.

## Acceptance
- [ ] foreign-user tests
- [ ] no fixture-user mode in prod config
- [ ] `make check` passes
