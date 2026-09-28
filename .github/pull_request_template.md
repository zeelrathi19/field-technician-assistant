## What changed and why

<!-- User-visible behaviour; task ID (T..); decision IDs (D..) if any. -->

## Evidence

<!-- Exact commands and results. Keep offline/scripted results separate from live-provider results. -->
- [ ] `make check`
- [ ] `make e2e` (if UI, API or turn loop touched)
- [ ] `make smoke` / `make smoke-codex` (if prompt or provider touched)

## Checklist

- [ ] The hard rules in AGENTS.md still hold (ownership, one-step status, strict tools, one write, verified answers)
- [ ] Docs updated (`docs/`, README) if behaviour or contracts changed
- [ ] No secrets, `.env`, databases or assignment PDF
- [ ] Handoff written (`agentctl handoff`) and claim released
