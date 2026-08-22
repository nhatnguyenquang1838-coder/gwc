# Slack Controller–Executor Protocol — MVP

Status: MVP pilot contract. Full E2E protocol is deferred.

## Purpose

Use Slack as a low-noise execution visibility and control surface between a GPT Controller and one Executor (Hermes in the pilot). Slack is not governance authority or source of truth.

## Canonical RootCard contract

`schemas/task-controller-root-card.schema.json` is the machine-readable semantic SOT for TaskController RootCards.
`tools/node_architect/slack_task_controller.py` is the deterministic compiler/validator for that contract.

Slack Canvas may define communication and layout policy only. Slack Block Kit, GG, and other platform renderers are projections of a validated RootCard payload. They must not redefine fields, repair invalid payloads, synthesize missing semantic state, or reconstruct navigation URLs.

## RootCard

One root message per run. The RootCard is a fast human snapshot and is updated in place.

Required fields:
- Human owner / watcher
- Gate journey G0 → G6 with current gate highlighted
- Controller and Executor identity
- Executor model when runtime exposes it
- Token usage when runtime exposes it, otherwise `N/A`
- Cost: `FREE | metered | unknown`; never infer
- Active subtask and progress
- Branch / PR / HEAD / CI
- Risk / blocker
- `Now` and `Next`
- Last material update
- Conversation navigation when ChatGPT is the Controller

### Conversation navigation

For a ChatGPT Controller, the RootCard MUST bind:
- `conversation.platform = chatgpt`
- `conversation.source = gpt_runtime_current_chat`
- the exact runtime-supplied URL of the current ChatGPT chat in `conversation.deeplink`

The deeplink is opaque runtime data. The contract does **not** require a separate `conversation_id` and does **not** define one canonical route shape such as `/c/<id>`.

`Open in GPT` is compiler-derived from that exact `deeplink`. Callers and renderers must not provide or override an independent `Open in GPT` URL.

Forbidden:
- `https://chatgpt.com/` or any generic ChatGPT home/landing fallback
- shared/public conversation links such as `/share/...`
- fabricated or reconstructed conversation URLs
- substituting task ID, run ID, GPT ID, or any other identifier for the actual current-chat URL
- rewriting a valid runtime-supplied current-chat URL to another assumed route shape

If the exact current-chat URL is missing or invalid, RootCard compilation fails closed. A renderer must not show a fallback `Open in GPT` action. A valid deeplink is passed through unchanged, including its supported GPT-specific route, query, and fragment.

Contextual actions:
- `PAUSE`: soft control intent; stop before the next meaningful action boundary
- `STOP`: hard stop intent; start no new mutation and return stopped/blocked state
- `APPROVE`: visible only when an exact human authority boundary exists; button intent is not authority by itself
- `MERGE`: visible only when merge is a valid next action and exact PR/head is bound; button intent is not authority by itself
- `Open in GPT`: navigation only; compiler-derived from the validated exact current-chat deeplink

## Controller Plan & Contract

Controller decomposes the selected execution option into 3–5 meaningful subtasks. Do not forward rejected alternatives or brainstorming noise to the Executor.

Each subtask has exactly these fields:

```text
ID
Objective
Allowed work
Expected output
Report requirement
After report = CONTINUE | WAIT_CONTROLLER | TERMINAL
```

Controller must define which milestones require a Slack report and what evidence must be included.

## Executor thread update

Executor reports at contracted subtask/milestone boundaries and material exceptions.

Template:

```text
🟡 EXECUTOR UPDATE · Sx/y
Status: <RUNNING|DONE|BLOCKED|FAILED>
Phase: <phase>

Completed
• meaningful result

Evidence
• exact material evidence

Finding / Risk
• only when material

Next
→ exact next action

Sx · <CONTINUE|WAIT_CONTROLLER|TERMINAL>
```

Report immediately for:
- scope drift
- authority drift
- evidence conflict
- blocker/failure
- material finding that invalidates the current plan

Remain silent for:
- chain-of-thought or internal planning narration
- tool invocation chatter
- individual file reads/edits
- raw terminal/test/CI JSON output
- repetitive CI polling
- recovered transient retries
- low-level successful operations that do not change human understanding

Rule: tool output is silent; semantic consequence is visible.

## Controller monitoring loop

For an active run:

```text
send contract / command
→ sleep 60s in-session
→ read only thread replies newer than last_seen_ts
→ compare report with expected subtask/milestone
→ OK: continue polling or release next step
→ WAIT_CONTROLLER: review before release
→ DRIFT: INTERCEPT
→ terminal: leave current control loop
```

Polling itself produces no Slack message.

MVP intercept conditions only:
1. scope drift
2. authority drift
3. plan drift
4. evidence conflict
5. material finding that invalidates the contracted next step

Do not intercept harmless tool-choice differences, successful retries, normal progress, or ordinary test runtime.

## Pilot topology

```text
1 task
1 GPT Controller
1 Hermes main Executor
1 Slack RootCard/thread
3–5 subtasks
1 in-session 60s polling loop
```

The pilot should include one safe controlled drift to verify intercept behavior.

## Deferred Full E2E

Do not add these to MVP unless the pilot proves they are needed:
- typed event envelopes
- command sequence / lease fencing
- idempotency / replay protection
- durable callback bridge
- disconnect/thread recovery
- command/result digests
- takeover semantics
- multi-executor / parallel execution
