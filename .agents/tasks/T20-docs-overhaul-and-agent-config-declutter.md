---
id: T20
title: Docs overhaul and agent-config declutter
status: done
priority: P1
owner: claude-opus
depends_on: []
paths: [docs/**, README.md, AGENTS.md, CLAUDE.md, DECISIONS.md, AI_USAGE.md, architecture-guide.html, IMPLEMENTATION_PLAN.md, tools/agentctl.py, tools/githooks/**, .githooks/pre-commit, Makefile, .github/copilot-instructions.md, .github/pull_request_template.md, .github/workflows]
---

## Goal
Current, navigable docs; only AGENTS.md + CLAUDE.md as agent config

## Acceptance
- [x] tests added and `make check` passes
