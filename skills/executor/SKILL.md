---
name: executor
description: Execute a bounded TaskController contract through the Slack Controller–Executor MVP, reporting only contracted milestones/material exceptions and respecting CONTINUE, WAIT_CONTROLLER, and TERMINAL boundaries.
when_to_use: Use when Hermes or another execution agent receives a validated bounded Controller contract for implementation.
version: 0.1.0
project: gwc
owner: GWC
---

# Executor Skill

## Canonical sources

Load normal coding-agent/GWC bootstrap, then `agents/shared/slack-controller-executor-protocol.md` and the Executor-specific overlay (Hermes: `agents/hermes/agent-instructions.md`).

## Rules

Execute only the bounded selected option, allowed work/actions, subtask order, report requirements, and WAIT points supplied by TaskController. Do not infer authority from Slack, history, memory, buttons, prior approvals, or completion.

Report at contracted milestones using the shared Executor Update structure. Immediately report scope drift, authority drift, plan-invalidating findings, evidence conflict, blocker, or failure. Tool chatter, internal planning, individual file operations, raw test/CI output, repetitive polling, and recovered transient retries remain silent.

At `WAIT_CONTROLLER`, do not begin the next subtask. `TERMINAL` ends the delegated segment; it does not grant G3/G4/merge authority.
