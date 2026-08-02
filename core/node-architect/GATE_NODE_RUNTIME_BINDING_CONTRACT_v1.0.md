# Gate–Node Runtime Binding Contract v1.0

## 1. Purpose

GWC gates are the authority plane. Node Architect nodes are the execution plane.
A validated gate artifact may authorize an action, but it does not identify the
executable node. A route decision may identify a node, but it never grants
authority. Both must be valid before an execution action occurs.

## 2. Mandatory sequence

For every G2 repository mutation:

1. Rehydrate the task-scoped G0 context snapshot, G1 decision, G2 execution
envelope, exact approval receipt, work-item claim, and protected-base readback.
2. Resolve exactly one route from the canonical route profile.
3. Verify the selected node contract, registry entry, maturity, implementation,
graph revision, and profile revision.
4. Execute only the action already authorized by G2.
5. Route a successful repository write to `repo_delivery.diff-readback`.
6. Resolve the next node or the exact human gate. Do not stop at an ambiguous
conversation state or wait for a generic continuation prompt.

## 3. Authority invariant

A route decision must set all authority fields to `false`. Authority comes only
from validated gate artifacts and exact human approval where required. A node,
profile, implementation, connector, Jira state, branch, commit, or CI result
cannot create or expand authority.

## 4. Fail-closed reason codes

- `NODE_CONTEXT_NOT_LOADED`
- `NODE_ROUTE_MISSING`
- `NODE_ROUTE_AMBIGUOUS`
- `NODE_CONTRACT_MISSING`
- `NODE_CONTRACT_INCOMPLETE`
- `NODE_IMPLEMENTATION_UNAVAILABLE`
- `NODE_NOT_EXECUTABLE_AT_MATURITY`
- `GATE_NODE_BINDING_MISMATCH`
- `GRAPH_REVISION_DRIFT`
- `PROFILE_REVISION_DRIFT`

When any code applies, the outcome is `BLOCKED`, no implementation is invoked,
and no write or later-gate authority is granted.

## 5. Canonical G2 route

The `repository_write` action at `G2_EXECUTION` must resolve to
`repo_delivery.scoped-file-write`. A PASS continues to
`repo_delivery.diff-readback`. A successful exact diff readback continues to
`gate_authority.gate-transition-decision`, which may identify `G3_PR` as the
next authority boundary but may not create the G3 artifact or Draft PR without
the applicable G3 contract.

## 6. Revision binding

The profile binds to exact node-registry and runtime-graph revisions. A mismatch
is not an informational warning; it is a blocking drift condition requiring a
new profile revision or refreshed gate evidence.
