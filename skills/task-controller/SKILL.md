---
name: task-controller
description: Boot and operate an autonomous task as a Slack-mediated Controller: resolve DAG/authority, compile the selected G1 option plus exact G2 boundary into a bounded Executor contract, monitor milestone reports, intercept drift, and route later gates.
when_to_use: Use when an autonomous agent starts a governed task, delegates bounded work to an Executor over Slack, or resumes an active Controller run.
version: 0.1.0
project: gwc
owner: GWC
---

# TaskController Skill

## Canonical sources

Load repository governance first, then:
1. `agents/autonomous-agent/agent-instructions.md` for autonomous boot;
2. `agents/shared/slack-controller-executor-protocol.md`;
3. the platform Controller overlay, e.g. `agents/chatgpt-agent/slack-controller-mvp.md`;
4. `tools/node_architect/slack_task_controller.py` for deterministic contract compilation/classification.

## Contract

TaskController selects only a canonical DAG-ready + authorized task. It compiles **only the selected G1 option** and exact derived G2 authority into 3–5 subtasks with fields:
`ID`, `Objective`, `Allowed work`, `Expected output`, `Report requirement`, `After report`.

`After report` is exactly `CONTINUE | WAIT_CONTROLLER | TERMINAL`.

Slack is a control/visibility surface, never authority. RootCard is one root message per run; semantic milestone updates stay in its thread. Poll active runs incrementally every 60 seconds without posting polling chatter.

At Executor terminal evidence, re-read exact refs before CI/G3/G4 routing. At G4 pre-prod, invoke independent audit; do not merge based on Controller or Executor self-review.
