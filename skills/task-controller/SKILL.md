---
name: task-controller
description: Boot and operate a bounded autonomous task through the bound execution provider: resolve DAG/authority, compile the selected G1 option plus exact G2 boundary into a bounded Executor contract, maintain a canonical RootCard, monitor milestone reports, intercept drift, and route later gates.
when_to_use: Use when an autonomous agent starts a governed task, delegates bounded work through the current execution provider, or resumes an active Controller run.
version: 0.2.1
project: gwc
owner: GWC
---

# TaskController Skill

## Canonical sources

Load repository governance first, then:
1. `agents/autonomous-agent/agent-instructions.md` for autonomous boot;
2. `schemas/task-controller-root-card.schema.json` as the machine-readable RootCard semantic SOT;
3. the bound execution-provider contract and applicable runtime sources;
4. `agents/shared/slack-controller-executor-protocol.md` and the platform Controller overlay only when the current structured `RunState`/`RuntimePlan` explicitly binds the Slack adapter;
5. `tools/node_architect/slack_task_controller.py` only for that explicitly bound Slack compatibility route.

The Slack protocol is a compatibility overlay, not a default execution path. Slack Canvas is communication/layout policy only. Slack Block Kit, GG, and other renderers are projection/action transports only. They must consume validated canonical RootCard state and must not introduce a second semantic SOT.

## Contract

TaskController selects only a canonical DAG-ready + authorized task. It compiles **only the selected G1 option** and exact derived G2 authority into 3–5 subtasks with fields:
`ID`, `Objective`, `Allowed work`, `Expected output`, `Report requirement`, `After report`.

`After report` is exactly `CONTINUE | WAIT | RETRY | REPAIR | REPLAN | TERMINAL`.

The current structured `RunState`/`RuntimePlan` selects the route and provider. Slack is a control/visibility surface only when that binding explicitly selects the Slack compatibility adapter; otherwise the bound execution provider is authoritative and Slack is optional projection. For an explicitly bound Slack route, the current legacy adapter accepts only `CONTINUE | WAIT_CONTROLLER | TERMINAL`; `WAIT` may project to `WAIT_CONTROLLER`, while `RETRY`, `REPAIR`, and `REPLAN` remain typed and unsupported by that legacy adapter pending M2/R2 work. RootCard is one root message per run; semantic milestone updates stay in its bound reporting surface. Poll active runs incrementally without posting polling chatter.

## RootCard enforcement

For ChatGPT Controller runs, RootCard compilation requires the exact URL of the **current ChatGPT chat created/owned by the GPT runtime**, bound as `source=gpt_runtime_current_chat`. The URL is opaque runtime data: the contract does not require a separate `conversation_id` and does not pin navigation to a `/c/...` route shape.

`Open in GPT` is derived by the compiler from that exact URL. Never fall back to ChatGPT home, a share/public URL, a reconstructed URL, or a task/run/GPT identifier. Renderers preserve the validated deeplink unchanged. Missing or invalid current-chat navigation fails closed instead of producing a misleading `Open in GPT` action.

At Executor terminal evidence, re-read exact refs before CI/G3/G4 routing. At G4 pre-prod, invoke independent audit; do not merge based on Controller or Executor self-review.
