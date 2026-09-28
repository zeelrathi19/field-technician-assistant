# Handoff

## Current state

The user confirmed **detailed implementation-ready plan and HTML guide first**. This repository-shaped package contains design documents and unchanged supporting inputs. No backend/frontend runtime, dependency lockfiles, live-model integration, commits, remote repository, or deployment is claimed.

## Next authorized work after an implementation request

1. Read AGENTS.md and the plan/contract documents.
2. Freeze the provider/model settings and contracts; verify installed-compatible dependency versions.
3. Implement the policy/data, model/context, and UI work streams using assigned file ownership.
4. Integrate, run the acceptance matrix, verify one-command startup and real provider behavior.
5. Update this handoff, README, DECISIONS and HTML with actual results.

## Inputs still needed at the relevant stage

- Implementation: a supported model identifier and provider API key configured locally for live testing. Fake-provider tests need no key.
- First commit: Zeel Rathi's verified commit email (or existing verified authorized local identity). Name is already specified.
- Remote push: destination repository URL, intended private reviewer access and normal secure git authentication. Never store a token in project files, a remote URL or a command transcript.

These do not block the completed planning work. No token is required to read the HTML or use the plan.

## Atomic project learnings

| Observation | Evidence | Consequence |
|---|---|---|
| Status chain contains mandatory On Hold between In Progress and Completed | Assignment page 2 | Implement literal adjacent transitions, even if atypical operationally |
| Corpus has five short sections | inputs/knowledge.md | Fit complete sections in initial context; avoid vector infrastructure |
| Fixture principal is tech-ravi | inputs/work_orders.json | Service owns this local-demo identity; reject chat-supplied identity |
| WO-003 starts On Hold; WO-001 starts In Progress | Supplied fixture | First is positive completion scenario; second is illegal-jump scenario |
| WO-008 mentions firmware but KB has no firmware procedure | Compare fixture with knowledge | Task list is not evidence for repair instructions |
| At-most-one-write alone cannot stop a model substituting an intermediate status | Guardrail design review | Check proposal against the user's explicit destination |
| Submission requires working source, not documentation alone | Assignment page 3 | Plan package must remain labelled until implementation is verified |

## Implementation completion report template

```text
Task / owner / branch:
Requirement IDs covered:
Files changed:
Contract changes:
Checks run (exact command, outcome):
Live-provider checks (model/date, outcome or blocker):
Remaining risks / failed checks:
Next concrete action:
Decision IDs added/changed:
```
