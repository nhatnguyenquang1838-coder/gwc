# Impact Analysis

## Task Scope

This task is tightly bounded to the current `intake_context` family. The primary change is the `request-intake` node contract, with supporting validator and regression test updates.

## Directly Affected Paths

- `core/node-architect/node-catalog/intake_context/request-intake.node.json`
- `tools/node_architect/validate_node_catalog_intake_context.py`
- `tests/test_node_catalog_intake_context.py`
- `core/node-architect/node-catalog/intake_context/README.md`

## Adjacent Paths to Keep Consistent

- `core/node-architect/runtime-graph-registry.json`
- `core/node-architect/node-registry.json`
- `core/KIRO_SPEC_DRIVEN_DELIVERY_RULE_v1.0.md`
- `core/runbooks/GATE_G0_G1_OPERATIONAL_RUNBOOK_v1.0.md`

## Inference From Evidence

The current node descriptor is still a compact G0 read-only workflow record. That means any typed intake contract must preserve the gate and authority boundary while adding machine-readable semantics on top of the existing node identity.

## Expected Behavior Change

- The node should expose a stable normalized intake shape.
- The validator should reject malformed or ambiguous request payloads.
- Tests should prove the same input normalizes the same way every time.
- Evidence capture should be reproducible from the exact repository head.

## Non-Goals

- No production behavior changes outside the node catalog.
- No new connector, scheduler, or write authority.
- No external task-system mutation.
