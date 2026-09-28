# Implementation agent instructions

This package is currently a plan. The user requested the implementation-ready plan and HTML guide first. Do not infer authorization to publish or claim that application code already exists. If subsequently asked to implement, follow this document and the frozen contracts.

## Read before working

1. README.md and IMPLEMENTATION_PLAN.md.
2. docs/contracts.md, docs/memory-and-prompts.md and docs/guardrails.md.
3. docs/acceptance-tests.md, docs/delivery-and-workflow.md and DECISIONS.md.
4. Your assigned task, ownership boundaries and latest docs/handoff.md.

`docs/contracts.md` owns exact API/schema names and default limits. The source assignment owns its required business invariants; IMPLEMENTATION_PLAN.md maps them. If another document conflicts with contracts, flag and reconcile the conflict before dependent code. Do not silently pick the easier interpretation.

## Non-negotiable shared model

- LLM proposes; typed backend code authorizes; SQLite commits; renderer reports receipts.
- Exact four tools. No eval, arbitrary dispatch, SQL generation, shell, browser, or configuration tools.
- Fresh ownership on every tool, server-owned principal, exact adjacent status path.
- Explicit target/action/payload binding; one mutation per turn; no intermediate workaround.
- Unknown/malformed calls fail closed. No prompt can disable a rule.
- KB facts are cited complete approved sections; absence means abstention, not guessing.
- Session focus is not authority; ambiguity clarifies; foreign/missing ID clears old focus.
- Two model attempts and two tool calls per turn maximum; retries count.
- Current package is planning only; record actual evidence before marking implementation complete.

## Parallel development protocol

The user requests parallel subagents where work is independent. After contracts are frozen, use bounded backend-policy, model/context, and UI tasks. Each subagent reads the whole shared model above and relevant contracts. Give exclusive file ownership; one integration owner changes shared contracts, locks and wiring. Use isolated worktrees for concurrent branch edits when available. Do not run concurrent git checkout/index operations in the same working tree.

A subagent completion report must include: files changed; requirement IDs covered; checks actually run and results; unresolved risk; contract changes; next action. Contract changes need integration review before dependent work continues. Do not add runtime multi-agent orchestration merely because development uses subagents.

## Quality and decisions

Use typed Python, composition, small cohesive classes and a plain React UI. A provider protocol and repository boundary are useful seams; abstraction factories, speculative adapters and deep inheritance are not required. Make error paths explicit; preserve failure semantics.

For a material decision record: ID, decision, why, alternative rejected, consequence, verification/revisit trigger. Keep DECISIONS.md around half a page; put the full register in docs/decision-log.md. Record an atomic learning as one observation + evidence + consequence; label untested hypotheses. Never request/store private chain-of-thought or repeat undocumented personal memories as project facts.

Use feature/fix/docs branches and PR review, never direct feature work on main. All commits use Zeel Rathi as author and committer name, with user-verified email. Do not invent the email or change global git config. No API tokens, .env, databases, transcripts, or assignment PDF in Git. Follow user-authorized remote setup through secure credential tooling; never embed a token in a URL.

## Done means evidence

Implement the required checks in the acceptance matrix. Run tests for policy/data/model contracts and actual browser behavior; record real-provider testing separately from fake-model tests. Keep README short and runnable. Update HTML and docs when contracts change. A failing/missing required check remains open, even if a deadline is near.
