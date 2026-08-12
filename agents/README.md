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