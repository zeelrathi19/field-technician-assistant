---
id: T08
title: Agent-agnostic multi-agent workspace
status: done
priority: P1
owner: claude-opus
depends_on: []
paths: [AGENTS.md, CLAUDE.md, GEMINI.md, CONVENTIONS.md, .cursor/**, .windsurf/**, .clinerules/**, .github/copilot-instructions.md, .gemini/**, .aider.conf.yml, tools/agentctl.py, tools/tests/**, .agents/README.md, .agents/templates/**, .githooks/**]
---

## Goal
Canonical AGENTS.md + generated pointers; agentctl claims/worktrees/handoffs.

## Acceptance
- [x] agentctl tests pass
- [x] doctor ok
- [x] `make check` passes
