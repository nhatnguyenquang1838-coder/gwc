# SCRUM-374 M‑05 Execution throttle control NA81 maturity

## Type

```text
feature
```

## Summary

Promotes `scale_control.execution-throttle-control` to an NA81-maturity
instruction-backed executable node with current-task test evidence binding the
SCRUM-374 brief (#309). The node already existed as a provenance-pinned
SCRUM-251/252 control (`tools/node_architect/execution_throttle_control.py`)
plus a closed decision schema
(`schemas/execution-throttle-decision.schema.json`); this maturity PR adds the
missing NA81 instruction card, test coverage, and changelog provenance, leaving
the descriptor and existing source untouched (provenance-SHA trap avoided).

The throttle decision is a deterministic capacity control that admits at most
one sequential implementation batch with bounded parallelism, preserves
active-lane ordering, and never grants task or gate authority (family
invariants):

- Single sequential batch: more than one active implementation batch is
  rejected as `ACTIVE_BATCH_CONCURRENCY_LIMIT_EXCEEDED`; an active batch that is
  not the current `batch_id` is rejected as `OTHER_BATCH_ALREADY_ACTIVE`.
- Previous-batch terminal gate: a non-terminal previous batch blocks admission
  (`PREVIOUS_BATCH_NOT_TERMINAL`).
- Deterministic capacity bound: throttling occurs on failure-signal cooldown
  (`FAILURE_SIGNAL_COOLDOWN`), insufficient capacity (`INSUFFICIENT_CAPACITY`),
  and when the requested rate exceeds what capacity or policy allows
  (`CAPACITY_BOUNDED_THROTTLE`, with `partial_execution_allowed` flagged).
- Every authority field is fixed `False`; admission decisions never grant merge,
  deployment, production, audit, or scale authority.
- Fail-closed deterministic input validation: missing identity, invalid SHA,
  invalid capacity, or invalid failure-rate inputs are rejected without side
  effects or network access.

## Guardrails

```text
EXECUTION_THROTTLE_PRESERVES_ACTIVE_LANE_ORDERING.
SINGLE_SEQUENTIAL_BATCH_ADMISSION_ENFORCED.
EXACT_HEAD_SHA_BINDING_IS_REQUIRED_FOR_EVIDENCE.
SCALE_CONTROL_THROTTLE_DOES_NOT_GRANT_TASK_OR_GATE_AUTHORITY.
```

## Wiring

- New node instruction card
  `core/node-architect/node-instructions/scale_control/execution-throttle-control.node-instruction.yaml`
  (validated against `schemas/node-architect/node-instruction.schema.json`;
  first `scale_control` instruction card; authority boundary fixed `False`).
- New NA81 test `tests/test_execution_throttle_control_na81.py` binds the #309
  brief to the existing executable and validates the closed decision schema.
- Changelog fragment only; no `*.node.json` `description`/`source` fields edited
  and no registry `source_sha` mutated (provenance-SHA trap avoided).

Parent authority: AR-SCRUM288-RECERT-20260814-R10 (issue #232), task SCRUM-374.
Targets pre-prod only; main is FORBIDDEN.
