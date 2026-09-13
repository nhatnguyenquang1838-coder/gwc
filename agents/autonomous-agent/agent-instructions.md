# Autonomous Agent — Universal Run Boot Overlay

Use this overlay only when the current structured RunState/RuntimePlan explicitly
binds an autonomous compatibility route. Slack is an optional compatibility adapter,
not the default runtime. A fresh run without that binding uses
`UNIVERSAL_RUN_NEW_RUNTIME` from the base runtime contract.

This overlay is additive to normal repository/agent instructions and does not
create authority.

## Boot role

The Autonomous Agent starts as **TaskController**. It does not begin by invoking a generic E2E executor.

Boot sequence:

1. refresh exact repository/base state and the canonical DAG;
2. load the current Parent/Child RunState, RuntimePlan, NodeAllocation, and
   authority/effect receipts;
3. resolve the current structured route and select only an authorized READY task;
4. claim using the canonical tracker/claim mechanism;
5. load the Slack protocol only when the current structured route explicitly
   binds the Slack compatibility adapter;
6. compile a minimal execution contract from G0 + selected G1 option + exact
   current authority;
7. dispatch through the bound execution provider and remain in-session until a
   typed continuation outcome is persisted;
8. monitor semantic milestone reports and intercept only contract-defined
   material drift.

Slack is communication/projection only. A Slack message, button, ACK, Executor completion, or Controller instruction does not create GWC authority.

## Controller / Executor boundary

The TaskController owns decomposition, 3–5 contracted subtasks, report milestones, WAIT points, evidence expectations, intercepts, and later-gate routing.

The Executor owns bounded implementation inside that contract. For Hermes, use `agents/hermes/agent-instructions.md` plus the shared Slack protocol. Do not ask the Executor to invent authority, select a different G1 option, widen scope, or choose arbitrary reporting cadence.

## Delivery boundary

After Executor terminal evidence:

`implementation -> exact-head CI -> independent G3 -> G4_PREPROD_AUDIT_TRIGGER`.

G4 pre-prod must invoke an independent `agent-audit` using `skills/audit-guardrail/SKILL.md`. Audit PASS is evidence only and feeds the standing G4 evaluator. Audit BLOCK returns to the TaskController for bounded repair/retry or safe stop.

Only the standing G4 evaluator may produce the merge decision. The audit agent has no merge, approval, mutation, deploy, release, production, secret, data, config, or migration authority.

After governed merge to `pre-prod`, refresh tracker/DAG state and continue the next eligible node. Human G4 remains the boundary for `pre-prod -> main`.
