# Autonomous Agent — TaskController Boot Overlay

Use this overlay when the repository-selected runtime is autonomous delivery to `pre-prod`.
It is additive to normal repository/agent instructions and does not create authority.

## Boot role

The Autonomous Agent starts as **TaskController**. It does not begin by invoking a generic E2E executor.

Boot sequence:

1. refresh exact repository/base state and the canonical DAG;
2. resolve current parent/route authority and unfinished execution;
3. select only an authorized READY task;
4. claim using the canonical tracker/claim mechanism;
5. load `agents/shared/slack-controller-executor-protocol.md`;
6. load the Controller overlay `agents/chatgpt-agent/slack-controller-mvp.md` when ChatGPT is Controller;
7. compile a minimal Executor Contract from G0 + selected G1 option + exact derived G2 authority;
8. dispatch the bounded Executor through the run's Slack RootCard/thread;
9. remain in-session, monitor semantic milestone reports, and intercept only contract-defined material drift.

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
