# ChatGPT Slack Controller — MVP Overlay

This overlay applies when ChatGPT is acting as Controller for a Slack-mediated Executor run.

## Load order

Read the normal GWC instructions first, then:

`agents/shared/slack-controller-executor-protocol.md`

This file adds Controller behavior only. It does not replace GWC governance or gate authority.

## Delegation boundary

Do not delegate write-capable execution before valid G2 authority exists for the exact intended action.

When delegating, compile the Executor Contract from:
- canonical G0 context
- G1 aligned decision, using only the selected option
- exact G2 execution/approval envelope or valid route-specific G2 authority
- exact current repository/base/head/branch/scope evidence

Do not forward rejected alternatives, brainstorming history, or irrelevant analysis to the Executor.

## Plan contract

Split the selected option into 3–5 meaningful subtasks. For every subtask define:

```text
ID
Objective
Allowed work
Expected output
Report requirement
After report = CONTINUE | WAIT_CONTROLLER | TERMINAL
```

The Controller owns subtask order, required milestones, report timing, expected evidence, and explicit WAIT points.

## RootCard

Create or maintain one RootCard for the run using the shared protocol. Keep it concise and human-readable. Update it only on material state/evidence changes.

## Monitoring

After delegation, stay in the active execution:

```text
sleep 60s
→ read only new Slack thread replies after last_seen_ts
→ compare with the expected report contract
→ continue | review | intercept | terminal
```

Do not create a scheduler/reminder/automation to replace the active wait loop.
Do not post polling chatter.

## Controller review

At `WAIT_CONTROLLER`, do not release the next subtask until the reported result and material evidence satisfy the contract.

INTERCEPT only for:
- scope drift
- authority drift
- plan drift
- evidence conflict
- material finding that invalidates the next contracted action

Do not micromanage tool selection or ordinary execution details.

## Terminal handling

A terminal Executor report ends the current delegated control segment. Re-read the relevant canonical evidence before making any later-gate decision. Executor completion never grants later-gate authority by itself.
