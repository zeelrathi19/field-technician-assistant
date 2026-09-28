---
id: T07
title: Delivery: Docker, compose, Makefile, e2e, secret scan
status: done
priority: P1
owner: claude-opus
depends_on: [T06]
paths: [Dockerfile, compose.yaml, Makefile, .dockerignore, .env.example, e2e/**, tools/scan_secrets.py, .github/workflows/**]
---

## Goal
One-command launch and CI.

## Acceptance
- [x] compose config valid
- [x] image layout reproduced and served
- [x] `make check` passes
