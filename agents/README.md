# Agent Instruction Index

This directory contains agent-specific overlays. Base repository governance remains authoritative.

## Slack Controller–Executor MVP

When ChatGPT is acting as Controller for a Slack-mediated Executor run, it must first verify that the current structured `RunState`/`RuntimePlan` explicitly binds Slack, including a validated current `RunState`/`RuntimePlan` route ID and adapter identity. Only then is the following additive instruction chain mandatory:

1. normal GWC boot and `agents/chatgpt-agent/agent-instructions.md`
2. `agents/shared/slack-controller-executor-protocol.md`
3. GPT Controller: `agents/chatgpt-agent/slack-controller-mvp.md`

Natural-language Slack descriptions alone cannot select the compatibility route; otherwise use the bound execution provider and keep Slack optional projection.

For Hermes Executor, load the bound execution-provider contract and applicable GWC instructions. Load `agents/shared/slack-controller-executor-protocol.md` only when the current structured `RunState`/`RuntimePlan` explicitly binds the Slack adapter; otherwise the bound execution provider is authoritative and Slack remains optional projection.

The MVP is intentionally slim: one Controller, one Executor, one RootCard/thread, 3–5 contracted subtasks, milestone-based reporting, in-session 60-second incremental polling, explicit `CONTINUE | WAIT_CONTROLLER | TERMINAL` behavior, and bounded intercepts.

The GPT Controller owns decomposition, report timing, expected milestone evidence, WAIT points, review and intercept decisions. The Executor must not invent a different plan or arbitrary reporting cadence.

Full E2E sequencing/replay/recovery/multi-executor logic is deferred until pilot acceptance.

## Autonomous TaskController boot

For autonomous delivery, load `agents/autonomous-agent/agent-instructions.md` and `skills/task-controller/SKILL.md`. The autonomous agent starts as TaskController and dispatches bounded work through the bound execution provider; it loads the Slack MVP only when the current structured route explicitly binds that Slack compatibility adapter.

## Independent G4 pre-prod audit

At `G4_PREPROD_AUDIT_TRIGGER`, use `agents/agent-audit/agent-instructions.md` with `skills/audit-guardrail/SKILL.md`. The auditor is read-only, independent, exact-head-bound, and has `merge_authority=false`. A PASS receipt is evidence for the separate standing G4 evaluator; BLOCK returns to TaskController.
