---
id: T17
title: Review and harden backend policy and grounding
status: done
priority: P2
owner: claude-opus
depends_on: []
paths: [backend/app/intent.py, backend/app/grounding.py, backend/app/knowledge.py, backend/app/service.py, backend/app/domain.py, backend/tests/test_intent.py, backend/tests/test_grounding.py, backend/tests/test_knowledge.py, backend/tests/test_service.py, backend/tests/test_review_policy.py]
---

## Goal
Find and fix verified guardrail and grounding flaws with regression tests

## Acceptance
- [x] tests added and `make check` passes
