# Node Instruction Contract v1.0

## 1. Purpose

This contract defines the instruction pack that every route-selected executable
GWC Node Architect node must provide before an agent or runtime may invoke the
node implementation. It extends the gate-node binding contract without changing
gate authority.

GWC gates remain the authority plane. Node instructions remain execution-plane
constraints. A valid instruction card narrows execution; it never creates G2,
G3, G4, G5, or G6 authority.

## 2. Runtime invariant

```text
MODE_DOES_NOT_BYPASS_NODE_RUNTIME
```

Normal, fastlane, e2e, hotfix, and rescue execution may change validation depth,
batching, retry budget, or continuation strategy. None of those modes may bypass:

1. GWC boot;
2. agent task claim intake and readback;
3. independent gate-authority validation;
4. node route resolution;
5. node instruction validation;
6. node evidence and log recording;
7. next-node, next-action, or next-gate resolution.

A mode policy that disables any listed stage fails closed with
`MODE_BYPASSES_NODE_RUNTIME`.

## 3. Required instruction fields

Every executable node instruction card must contain:

```yaml
node_id:
gate:
purpose:
entry_conditions:
inputs:
allowed_actions:
forbidden_actions:
outputs:
evidence_required:
logs_required:
next:
retry:
rollback:
authority_boundary:
```

The repository schema may add metadata such as `schema_version`,
`artifact_type`, and `mode_policy`, but it must not weaken these fields.

## 4. Identity and gate binding

Before execution, the runtime must verify that:

- the route `current_node` equals the instruction `node_id`;
- the descriptor `node_id` equals the instruction `node_id`;
- the node registry contains the same canonical ID;
- the active gate is allowed by both descriptor and instruction card;
- the route profile references the exact instruction card;
- maturity and implementation availability checks still pass;
- all required context is non-empty and loaded.

A mismatch returns `NODE_INSTRUCTION_INVALID` or the earlier applicable
binding/drift failure code.

## 5. Evidence and log contract

Each node execution must persist or emit these canonical records:

```text
node-start
node-decision
node-result
node-readback
checkpoint
runtime-event
next-route-decision
decision_digest
state_digest
event_digest
```

Canonical task-scoped paths are:

```text
.gwc/tasks/<task-id>/node-runtime/<run-id>/<node-id>/node-start.json
.gwc/tasks/<task-id>/node-runtime/<run-id>/<node-id>/node-decision.json
.gwc/tasks/<task-id>/node-runtime/<run-id>/<node-id>/node-result.json
.gwc/tasks/<task-id>/node-runtime/<run-id>/<node-id>/node-readback.json
.gwc/tasks/<task-id>/node-runtime/<run-id>/<node-id>/checkpoint.json
.gwc/tasks/<task-id>/node-runtime/<run-id>/<node-id>/next-route-decision.json
.gwc/tasks/<task-id>/node-runtime/<run-id>/runtime-events.jsonl
```

`node-start` is recorded before an effectful implementation is invoked. Missing
evidence or log contracts fail closed before execution with
`NODE_EVIDENCE_CONTRACT_MISSING` or `NODE_LOG_CONTRACT_MISSING`.

Jira, Slack, Notion, and other projection systems may link to canonical evidence,
but projection readback cannot replace these records.

## 6. Next-route totality

The instruction `next` map must cover `pass`, `blocked`, `pending`, and `retry`.
Each applicable outcome must resolve at least one `next_node`, `next_action`, or
`next_gate`. The `pass` mapping must agree with the canonical route profile.
Missing or contradictory routing fails with `NODE_NEXT_ROUTE_MISSING`.

A next-gate result identifies an authority boundary only. It does not create the
next gate artifact and does not authorize the next gate action.

## 7. Retry and rollback

Retry rules must define:

- idempotency identity fields;
- replay/readback checks;
- a bounded retry limit;
- pending-effect reconciliation behavior.

Rollback rules must state whether local effects are reversible, what
reconciliation evidence is required, and when human authority is mandatory.
Retries must never create a second external effect merely because a response was
unknown or a session restarted.

## 8. Authority boundary

Every instruction card must explicitly set all gate and later-action authority
flags to false. Allowed actions must not include merge, auto-merge, deploy,
release, publish, runtime reload, production configuration/data, credential or
secret changes, migrations, force-push, branch deletion, shared-history rewrite,
or PR-base change unless a separate gate artifact and exact authority are
validated outside the node instruction.

Any instruction that grants or implies such authority fails with
`NODE_AUTHORITY_ESCALATION_ATTEMPT`.

## 9. Stable failure codes

```text
NODE_INSTRUCTION_MISSING
NODE_INSTRUCTION_INVALID
NODE_EVIDENCE_CONTRACT_MISSING
NODE_LOG_CONTRACT_MISSING
NODE_NEXT_ROUTE_MISSING
MODE_BYPASSES_NODE_RUNTIME
NODE_AUTHORITY_ESCALATION_ATTEMPT
```

These codes are additive to existing gate-node route failures. The earliest
applicable fail-closed condition wins; no implementation is invoked and all
authority fields remain false.

## 10. Initial executable vertical slice

The first instruction-backed route is:

```text
gate_authority.gate-state-resolution
→ repo_delivery.scoped-file-write
→ repo_delivery.diff-readback
→ gate_authority.gate-transition-decision
→ next_gate = G3_PR
```

Nodes outside a validated instruction-backed route remain catalog-only and must
not be treated as executable merely because they have a registry slot or
descriptor.
