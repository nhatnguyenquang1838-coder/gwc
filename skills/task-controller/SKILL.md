---
name: task-controller
description: Boot and operate an autonomous task as a Slack-mediated Controller: resolve DAG/authority, compile the selected G1 option plus exact G2 boundary into a bounded Executor contract, maintain a canonical RootCard, monitor milestone reports, intercept drift, and route later gates.
when_to_use: Use when an autonomous agent starts a governed task, delegates bounded work to an Executor over Slack, or resumes an active Controller run.
version: 0.2.1
project: gwc
owner: GWC
---

# TaskController Skill

## Canonical sources

Load repository governance first, then:
1. `agents/autonomous-agent/agent-instructions.md` for autonomous boot;
2. `schemas/task-controller-root-card.schema.json` as the machine-readable RootCard semantic SOT;
3. `agents/shared/slack-controller-executor-protocol.md`;
4. the platform Controller overlay, e.g. `agents/chatgpt-agent/slack-controller-mvp.md`;
5. `tools/node_architect/slack_task_controller.py` for deterministic contract/RootCard compilation and classification.

Slack Canvas is communication/layout policy only. Slack Block Kit, GG, and other renderers are projection/action transports only. They must consume validated canonical RootCard state and must not introduce a second semantic SOT.

## Contract

TaskController selects only a canonical DAG-ready + authorized task. It compiles **only the selected G1 option** and exact derived G2 authority into 3–5 subtasks with fields:
`ID`, `Objective`, `Allowed work`, `Expected output`, `Report requirement`, `After report`.

`After report` is exactly `CONTINUE | WAIT_CONTROLLER | TERMINAL`.

Slack is a control/visibility surface, never authority. RootCard is one root message per run; semantic milestone updates stay in its thread. Poll active runs incrementally every 60 seconds without posting polling chatter.

## RootCard enforcement

For ChatGPT Controller runs, RootCard compilation requires the exact URL of the **current ChatGPT chat created/owned by the GPT runtime**, bound as `source=gpt_runtime_current_chat`. The URL is opaque runtime data: the contract does not require a separate `conversation_id` and does not pin navigation to a `/c/...` route shape.

`Open in GPT` is derived by the compiler from that exact URL. Never fall back to ChatGPT home, a share/public URL, a reconstructed URL, or a task/run/GPT identifier. Renderers preserve the validated deeplink unchanged. Missing or invalid current-chat navigation fails closed instead of producing a misleading `Open in GPT` action.

At Executor terminal evidence, re-read exact refs before CI/G3/G4 routing. At G4 pre-prod, invoke independent audit; do not merge based on Controller or Executor self-review.
