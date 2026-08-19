# SCRUM-370 M‑05 Batch-admission-check NA81 maturity

## Type

```text
feature
```

## Summary

Promotes `scale_control.batch-admission-check` to an NA81-maturity
instruction-backed executable node with current-task test evidence binding the
SCRUM-370 brief (#305). The node already existed as a provenance-pinned
SCRUM-251/252 control (`tools/node_architect/batch_admission_check.py`) plus a
closed decision schema (`schemas/batch-admission-decision.schema.json`); this
maturity PR adds the missing NA81 instruction card, test coverage, and changelog
provenance, leaving the descriptor and existing source untouched (provenance-SHA
trap avoided).

The batch-admission decision is a deterministic, fail-closed gate control:

- Safe vs unsafe batches: when the previous-batch merge SHA matches G5 evidence,
  G5 CI is successful and qualified, G5 evidence is fresh, no active blocker is
  present, and the requested node count is within budget, the batch is admitted
  (`BATCH_ADMISSION_REQUIREMENTS_SATISFIED`); otherwise it is rejected with a
  stable reason code.
- Previous-batch merge integrity: a mismatch between `previous_merge_sha` and
  `g5_evidence_merge_sha` is rejected as `G5_MERGE_SHA_MISMATCH`.
- Fail-closed deterministic input validation: missing identity is rejected as
  `REQUIRED_IDENTITY_MISSING`, invalid SHA binding as
  `INVALID_OR_MISSING_SHA_BINDING`, invalid limit input as
  `INVALID_BATCH_LIMIT_INPUT`, and invalid G5 observation time as
  `INVALID_G5_OBSERVATION_TIME`.
- G5 CI gating: a non-successful G5 status is rejected as `G5_NOT_SUCCESSFUL`,
  unqualified G5 evidence as `G5_EVIDENCE_UNQUALIFIED`, and stale G5 evidence as
  `G5_EVIDENCE_STALE`.
- Blocker gating: a non-CLEAR blocker status is rejected as
  `ACTIVE_BLOCKER_PRESENT`.
- Budget gating: a requested node count above the approved budget is rejected as
  `APPROVED_NODE_BUDGET_EXCEEDED`.
- Determinism and idempotency: identical inputs yield a stable digest and
  identical decisions; the decision is computed purely in memory with no
  filesystem side effect.
- Every authority field is fixed `False`; admission decisions never grant merge,
  deployment, production, audit, or scale authority, and partial admission is
  never allowed.

## Guardrails

```text
PREVIOUS_BATCH_MERGE_SHA_IS_VERIFIED_AGAINST_G5_EVIDENCE.
G5_CI_SUCCESS_AND_QUALIFIED_IS_REQUIRED_FOR_ADMISSION.
EXACT_HEAD_SHA_BINDING_IS_REQUIRED_FOR_EVIDENCE.
BATCH_ADMISSION_CHECK_DOES_NOT_GRANT_TASK_OR_GATE_AUTHORITY.
```

## Wiring

- New node instruction card
  `core/node-architect/node-instructions/scale_control/batch-admission-check.node-instruction.yaml`
  (validated against `schemas/node-architect/node-instruction.schema.json`;
  authority boundary fixed `False`; the terminal admission gate routes to G3 PR
  creation with no later node).
- New NA81 test `tests/scale_control/test_batch_admission_check_na81.py` binds
  the #305 brief to the existing executable
  `node_architect.batch_admission_check` (imported via an absolute `tools/`
  path insertion so `python -m unittest discover` resolves it from the repo
  root) and validates the closed decision schema. 28 deterministic scenarios
  pass.
- Changelog fragment only; no `*.node.json` `description`/`source` fields edited
  and no registry `source_sha` mutated (provenance-SHA trap avoided).

Parent authority: AR-SCRUM288-RECERT-20260814-R10 (issue #232), task SCRUM-370.
Targets pre-prod only; main is FORBIDDEN.
