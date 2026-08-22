# SCRUM-371 M‑05 Batch-size-limit-check NA81 maturity

## Type

```text
feature
```

## Summary

Promotes `scale_control.batch-size-limit-check` to an NA81-maturity
instruction-backed executable node with current-task test evidence binding the
SCRUM-371 brief (#306). The node already existed as a provenance-pinned
SCRUM-251/252 control (`tools/node_architect/batch_size_limit_check.py`) plus a
closed decision schema (`schemas/batch-size-limit-decision.schema.json`); this
maturity PR adds the missing NA81 instruction card, test coverage, and changelog
provenance, leaving the descriptor and existing source untouched (provenance-SHA
trap avoided).

The batch-size-limit decision is a deterministic, fail-closed cardinality and
single-active-batch control:

- Safe vs unsafe batch sizes: under-limit batches are admitted
  (`BATCH_LIMITS_SATISFIED`); over-limit batches are rejected as
  `BATCH_SIZE_LIMIT_EXCEEDED`; an empty batch is rejected as
  `EMPTY_BATCH_NOT_ADMITTED`.
- Fail-closed deterministic input validation: missing identity, invalid SHA
  binding, invalid limit configuration, or invalid batch-list input are
  rejected with no side effects or network access.
- Batch mapping integrity: node/batch length mismatch, duplicate node id, and
  mixed batch identifiers are rejected.
- Single-active-batch concurrency: more than one prospective implementation
  batch (including an unknown/foreign active batch) is rejected as
  `ACTIVE_BATCH_CONCURRENCY_LIMIT_EXCEEDED`; the current `batch_id` active is
  admitted.
- Normalization: the prospective implementation-batch set is the sorted unique
  projection of the active batches plus the current batch.
- Determinism and idempotency: identical inputs yield a stable digest and
  identical decisions; the decision is computed purely in memory with no
  filesystem side effect.
- Every authority field is fixed `False`; admission decisions never grant merge,
  deployment, production, audit, or scale authority, and partial admission is
  never allowed.

## Guardrails

```text
BATCH_SIZE_LIMIT_IS_ENFORCED_WITHOUT_PARTIAL_ADMISSION.
SINGLE_ACTIVE_IMPLEMENTATION_BATCH_ENFORCED.
EXACT_HEAD_SHA_BINDING_IS_REQUIRED_FOR_EVIDENCE.
BATCH_SIZE_LIMIT_CHECK_DOES_NOT_GRANT_TASK_OR_GATE_AUTHORITY.
```

## Wiring

- New node instruction card
  `core/node-architect/node-instructions/scale_control/batch-size-limit-check.node-instruction.yaml`
  (validated against `schemas/node-architect/node-instruction.schema.json`;
  authority boundary fixed `False`; pass routes to
  `scale_control.batch-admission-check`).
- New NA81 test `tests/scale_control/test_batch_size_limit_check_na81.py` binds
  the #306 brief to the existing executable
  `node_architect.batch_size_limit_check` (imported via an absolute `tools/`
  path insertion so `python -m unittest discover` resolves it from the repo
  root) and validates the closed decision schema. 29 deterministic scenarios
  pass.
- Changelog fragment only; no `*.node.json` `description`/`source` fields edited
  and no registry `source_sha` mutated (provenance-SHA trap avoided).

Parent authority: AR-SCRUM288-RECERT-20260814-R10 (issue #232), task SCRUM-371.
Targets pre-prod only; main is FORBIDDEN.
