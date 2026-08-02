# Gate–Node Runtime Binding Contract v1.0

## 1. Purpose

GWC gates are the authority plane. Node Architect nodes are the execution plane.
A validated gate artifact may authorize an action, but it does not identify the
executable node. A route decision may identify a node, but it never grants
authority. Both must be valid before an execution action occurs.

## 2. Mandatory sequence

For every governed executable node, including normal, fastlane, e2e, hotfix, and
rescue execution:

1. Complete GWC boot and agent task claim intake.
2. Rehydrate task-scoped gate authority and required context.
3. Resolve exactly one route from the canonical route profile.
4. Verify registry entry, descriptor, maturity, implementation, graph revision,
   profile revision, and the node instruction contract.
5. Validate the instruction's evidence, logs, next-route, retry, rollback, mode,
   and authority boundary before invoking implementation.
6. Record node-start, decision, result, readback, checkpoint, runtime event,
   digests, and next-route decision in the canonical task/run/node ledger.
7. Continue only to the declared next node, action, or separately authorized gate.

## 3. Mode invariant

```text
MODE_DOES_NOT_BYPASS_NODE_RUNTIME
```

Fastlane, e2e, hotfix, rescue, and normal execution may alter validation depth,
batching, or continuation strategy. They must never bypass GWC boot, task claim,
gate authority, route resolution, node instruction validation, evidence/log
recording, or next-route resolution. A mode that disables any required runtime
stage fails closed with `MODE_BYPASSES_NODE_RUNTIME`.

## 4. Authority invariant

A route decision and node instruction must set all authority fields to false.
Authority comes only from validated gate artifacts and exact human approval where
required. Node instructions constrain execution; they do not grant G2, G3, G4,
G5, or G6 authority. CI success, Jira/Slack/Notion projection, node maturity, or a
route decision cannot create or expand authority.

## 5. Fail-closed reason codes

Existing route/runtime codes remain valid. Instruction-backed execution adds:

- `NODE_INSTRUCTION_MISSING`
- `NODE_INSTRUCTION_INVALID`
- `NODE_EVIDENCE_CONTRACT_MISSING`
- `NODE_LOG_CONTRACT_MISSING`
- `NODE_NEXT_ROUTE_MISSING`
- `MODE_BYPASSES_NODE_RUNTIME`
- `NODE_AUTHORITY_ESCALATION_ATTEMPT`

When any code applies, implementation is not invoked and no write or later-gate
authority is granted.

## 6. Canonical G2 route

```text
gate_authority.gate-state-resolution
→ repo_delivery.scoped-file-write
→ repo_delivery.diff-readback
→ gate_authority.gate-transition-decision
→ next_gate = G3_PR
```

The route identifies the next authority boundary only. It does not create the G3
artifact or Draft PR without the applicable G3 action authority.

## 7. Canonical evidence ledger

Every execution emits task-scoped evidence under:

```text
.gwc/tasks/<task-id>/node-runtime/<run-id>/<node-id>/node-start.json
.gwc/tasks/<task-id>/node-runtime/<run-id>/<node-id>/node-decision.json
.gwc/tasks/<task-id>/node-runtime/<run-id>/<node-id>/node-result.json
.gwc/tasks/<task-id>/node-runtime/<run-id>/<node-id>/node-readback.json
.gwc/tasks/<task-id>/node-runtime/<run-id>/<node-id>/checkpoint.json
.gwc/tasks/<task-id>/node-runtime/<run-id>/<node-id>/next-route-decision.json
.gwc/tasks/<task-id>/node-runtime/<run-id>/runtime-events.jsonl
```

The ledger is append/readback oriented and replay-safe. Jira, Slack, and Notion
remain projection-only and cannot replace canonical repository evidence.

## 8. Revision binding

The profile binds exact node-registry and runtime-graph revisions. A mismatch is
a blocking drift condition requiring refreshed profile or gate evidence.
