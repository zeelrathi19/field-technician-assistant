# .agents — shared workspace for parallel, multi-vendor coding agents

| Path | Committed | Purpose |
|---|---|---|
| `tasks/*.md` | yes | Task cards: front matter (`id, title, status, priority, owner, depends_on, paths`) + acceptance |
| `handoffs/*.md` | yes | One report per finished work session (`agentctl handoff`) |
| `LEARNINGS.md` | yes | Append-only atomic learnings: observation — evidence — consequence |
| `templates/` | yes | Handoff/task templates for agents that prefer to write by hand |
| `<git-common-dir>/agentctl/claims/*.json` | no | Live claims, shared by every worktree of this clone |
| `<git-common-dir>/agentctl/events.jsonl` | no | Audit trail of claim/release/handoff events |

Status flow for a task card: `todo → in_progress (claimed) → review → done` (or `blocked`).
`agentctl release <T> --status review` updates the card; commit it on your branch.

Rules of thumb:
1. `make context` first. 2. Claim with `worktree` (isolated branch + directory). 3. Only touch your `paths`.
4. `make check` green. 5. Handoff + release. 6. A reviewer (human or another agent) merges with `--no-ff`.
