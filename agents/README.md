# Agent Instruction Index

This directory contains agent-specific overlays. Base repository governance remains authoritative.

## Slack Controller–Executor MVP

When ChatGPT is acting as Controller for a Slack-mediated Executor run, the following additive instruction chain is **mandatory**:

1. normal GWC boot and `agents/chatgpt-agent/agent-instructions.md`
2. `agents/shared/slack-controller-executor-protocol.md`
3. GPT Controller: `agents/chatgpt-agent/slack-controller-mvp.md`

For Hermes Executor, load:

1. normal coding-agent/GWC bootstrap
2. `agents/shared/slack-controller-executor-protocol.md`
3. `agents/hermes/agent-instructions.md`

The MVP is intentionally slim: one Controller, one Executor, one RootCard/thread, 3–5 contracted subtasks, milestone-based reporting, in-session 60-second incremental polling, explicit `CONTINUE | WAIT_CONTROLLER | TERMINAL` behavior, and bounded intercepts.

The GPT Controller owns decomposition, report timing, expected milestone evidence, WAIT points, review and intercept decisions. The Executor must not invent a different plan or arbitrary reporting cadence.

Full E2E sequencing/replay/recovery/multi-executor logic is deferred until pilot acceptance.

## Autonomous TaskController boot

For autonomous delivery, load `agents/autonomous-agent/agent-instructions.md` and `skills/task-controller/SKILL.md`. The autonomous agent starts as TaskController and dispatches the bounded Executor through the existing Slack MVP rather than routing the claimed task to a generic E2E invocation.

## Independent G4 pre-prod audit

At `G4_PREPROD_AUDIT_TRIGGER`, use `agents/agent-audit/agent-instructions.md` with `skills/audit-guardrail/SKILL.md`. The auditor is read-only, independent, exact-head-bound, and has `merge_authority=false`. A PASS receipt is evidence for the separate standing G4 evaluator; BLOCK returns to TaskController.
