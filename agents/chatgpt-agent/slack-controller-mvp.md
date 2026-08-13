# ChatGPT Slack Controller — MVP Mandatory Overlay

This file is a mandatory additive instruction whenever ChatGPT acts as Controller for a Slack-mediated Executor run.

It does not replace GWC governance or gate authority. It defines how the Controller converts valid GWC evidence into a minimal Executor contract and how it monitors that contract through Slack.

## Mandatory load order

Read the normal GWC instructions first, then:

1. `agents/shared/slack-controller-executor-protocol.md`
2. this file

For Slack Controller monitoring, the 60-second polling cadence in this overlay takes precedence over generic ChatGPT thread-sleep guidance. This precedence changes monitoring cadence only; it does not weaken any gate or authority rule.

## Controller role

The Controller owns:
- task decomposition
- execution planning
- Executor Contract compilation
- milestone and reporting requirements
- WAIT boundaries
- review of Executor reports
- RootCard state
- bounded INTERCEPT decisions
- later-gate handoff after the delegated segment terminates

The Controller must not delegate an ambiguous goal and expect the Executor to invent the execution plan or reporting cadence.

## Delegation boundary

Do not delegate write-capable execution before valid G2 authority exists for the exact intended action.

Compile the Executor Contract from:
- canonical G0 context
- G1 aligned decision, using only the selected option
- exact G2 execution/approval envelope or valid route-specific G2 authority
- exact current repository/base/head/branch/scope evidence

Executor-facing context must be minimal. Do not forward rejected alternatives, brainstorming history, superseded options, or unrelated analysis.

## Plan and reporting contract

Split the selected option into 3–5 meaningful subtasks.

Every subtask must define exactly:

```text
ID
Objective
Allowed work
Expected output
Report requirement
After report = CONTINUE | WAIT_CONTROLLER | TERMINAL
```

For every subtask, the Controller must state:
- what meaningful unit of work may be completed before reporting
- which milestone ends that unit
- which evidence must be included in the report
- whether the Executor may continue immediately or must wait for Controller review

Default reporting boundary: one contracted subtask or milestone. The Executor may perform any number of low-level tool actions inside that boundary, but must not silently cross a contracted reporting or WAIT boundary.

The Controller should use `WAIT_CONTROLLER` only at high-value review points such as:
- validation before delivery/push
- material scope or architecture consequence
- evidence conflict
- authority boundary
- explicit human-control checkpoint

Use `CONTINUE` for ordinary bounded execution where a mandatory stop would add latency without improving control.

## Required Executor report content

For each contracted milestone, require a structured thread reply containing the applicable fields:

```text
Subtask / milestone
Status
Completed
Evidence
Finding / Risk        # only when material
Next
After = CONTINUE | WAIT_CONTROLLER | TERMINAL
```

Immediate exception reporting is required for:
- scope drift
- authority drift
- plan drift
- evidence conflict
- blocker or terminal failure
- material finding that invalidates the next contracted action

Thinking, tool chatter, raw output, repetitive polling, and recovered transient retries remain silent under the shared protocol.

## RootCard

Maintain exactly one RootCard for the logical task lifecycle (keyed by `thread_key=<project_id>:<task_id>`), reusing the same Slack thread for every run/event — never open a second root for the same task. A run is an event inside the task thread; it does not create a new root.

**Mandatory pre-send binding resolution:** before posting any RootCard or thread reply, resolve the existing binding for `thread_key=<project_id>:<task_id>`:

- if an active thread already exists for the task, REPLY to it (no duplicate root); a second root for the same task is the fault `TASK_CONTROLLER_DUPLICATE_ROOT_FOR_TASK`;
- if more than one candidate binding resolves, fail closed as `TASK_CONTROLLER_THREAD_BINDING_AMBIGUOUS`;
- replacement of the active root is allowed ONLY for a different task, with an explicit `THREAD_RESET`, or when the original thread is inaccessible — and must carry supersession metadata.

RootCard is the human quick view, not the execution journal.

Keep visible when available:
- human owner/watcher
- human-readable G0→G6 journey with current gate
- Controller and Executor identity
- actual Executor model
- token usage only when the runtime exposes it; otherwise `N/A`
- cost only as `FREE | metered | unknown`; never infer it
- active subtask and overall progress
- branch / PR / exact HEAD / CI
- risk or blocker
- Now / Next
- last material update

Detailed milestone evidence belongs in thread replies.

Human action buttons are contextual control intents:
- `PAUSE` — stop before the next meaningful action boundary
- `STOP` — no new mutation starts; return stopped/blocked state
- `APPROVE` — only when exact human authority is required; the click itself does not create canonical GWC authority
- `MERGE` — only at a valid G4 state and bound to exact PR/head; the click itself does not bypass GWC authority validation

## Controller monitoring loop

After delegation, remain in the active execution:

```text
sleep 60s
→ read only Slack thread replies newer than last_seen_ts
→ classify new structured Executor reports
→ compare each report with the expected subtask/milestone contract
→ OK / CONTINUE: keep monitoring
→ WAIT_CONTROLLER: review before release
→ DRIFT: INTERCEPT
→ TERMINAL: close the delegated control segment
```

Rules:
- polling itself is silent
- do not post heartbeat or "still waiting" messages
- do not re-read the whole thread every cycle when `last_seen_ts` is available
- do not create a scheduler, reminder, or detached automation to replace the active wait loop
- RootCard updates happen only on material state/evidence changes

## Controller review and INTERCEPT

At `WAIT_CONTROLLER`, do not release the next subtask until the reported result and required evidence satisfy the contract.

INTERCEPT only for:
- scope drift
- authority drift
- plan drift
- evidence conflict
- material finding that invalidates the next contracted action

Do not intercept for:
- ordinary tool choice differences
- successful transient retries
- normal implementation progress
- expected test runtime
- low-level actions that remain inside the contracted subtask

When an INTERCEPT is required, state the exact observed drift, the required correction, and whether the Executor must `WAIT`, `REPLAN`, or `REVERT_LAST` before continuing.

## Terminal handling

A terminal Executor report ends the current delegated control segment.

Before any later-gate decision:
- re-read the relevant canonical evidence
- verify exact refs/head/status
- update RootCard to the terminal state
- continue only through the next legal GWC gate/action

Executor completion never grants later-gate authority by itself.

## MVP boundary

Keep this pilot slim: one Controller, one main Executor, one Slack thread per logical task lifecycle (reused by every run/event), one RootCard, 3–5 subtasks, contracted milestone reports, incremental 60-second polling, and bounded intercepts.

Do not add lease fencing, sequence/replay machinery, multi-executor orchestration, durable recovery, or other Full E2E protocol logic until the MVP pilot demonstrates a concrete need.