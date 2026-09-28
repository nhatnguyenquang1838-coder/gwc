---
name: executor
description: Execute a bounded Universal Run contract through the bound execution provider, using Slack only as an explicit compatibility adapter and reporting only contracted milestones/material exceptions.
when_to_use: Use when Hermes or another execution agent receives a validated bounded Controller contract for implementation.
version: 0.1.0
project: gwc
owner: GWC
---

# Executor Skill

## Canonical sources

Load normal coding-agent/GWC bootstrap and the current RunState, RuntimePlan,
NodeAllocation, authority/effect receipts, and applicable instruction bundle.
The Slack protocol is an explicit compatibility overlay: load it only when the
current structured route binds the Slack adapter.

## Runtime boot precedence

For a fresh current structured run, `UNIVERSAL_RUN_NEW_RUNTIME` is the default.
Compatibility is explicit-only: the current RunState/RuntimePlan must bind and
validate the exact route ID and adapter identity. Prose, history, branch names,
old loop/todo state, Slack messages, prior PRs, and prior approvals do not select
or grant a route.

## Rules

Execute only the bounded selected option, allowed work/actions, subtask order,
report requirements, and typed continuation outcome supplied by the current
RunState/RuntimePlan. Do not infer authority from Slack, history, memory,
buttons, prior approvals, or completion.

Report at contracted milestones through the bound execution provider using its current report contract. When the current structured route explicitly binds the Slack adapter, project those milestones through the shared Slack Executor Update structure. Immediately report scope drift, authority drift, plan-invalidating findings, evidence conflict, blocker, or failure. Tool chatter, internal planning, individual file operations, raw test/CI output, repetitive polling, and recovered transient retries remain silent.

At `WAIT`, do not begin the next subtask unless the current Continuation
Supervisor releases the typed outcome. `WAIT_CONTROLLER` is a Slack-only legacy
projection. `TERMINAL` ends the delegated segment; it does not grant G3/G4/merge
authority.
