# SCRUM-372 M‑05 Previous-batch-g5-verification NA81 maturity

## Type

```text
feature
```

## Summary

Promotes `scale_control.previous-batch-g5-verification` to an NA81-maturity
instruction-backed executable node with current-task test evidence binding the
SCRUM-372 brief (#307). The node already existed as a provenance-pinned
SCRUM-251/252 control (`tools/node_architect/previous_batch_g5_verification.py`)
plus a closed decision schema
(`schemas/previous-batch-g5-verification-decision.schema.json`); this maturity
PR adds the missing NA81 instruction card, test coverage, and changelog
provenance, leaving the descriptor and existing source untouched (provenance-SHA
trap avoided).

The previous-batch G5 verification is a deterministic, fail-closed gate control:

- Verified connector evidence: when the previous PR is merged, the evidence head
  SHA matches the exact expected merge SHA, the evidence event is a push, the
  evidence branch is `main`, G5 evidence is fresh and successful, and the
  connector status is `CONFIRMED` with a valid workflow run id, the previous
  batch is `VERIFIED_CONNECTOR` (`EXACT_POST_MERGE_G5_CONFIRMED`); otherwise it
  is blocked with a stable reason code.
- Exact merge SHA binding: an evidence head SHA that does not match the expected
  merge SHA is rejected as `G5_HEAD_SHA_MISMATCH`.
- Previous-PR integrity: a previous PR that is not merged is rejected as
  `PREVIOUS_PR_NOT_MERGED`.
- Evidence event/branch gating: a non-push event is rejected as
  `PR_ONLY_EVIDENCE_NOT_QUALIFIED`; a non-`main` branch as `G5_BRANCH_MISMATCH`.
- G5 freshness/success gating: stale evidence is rejected as `G5_EVIDENCE_STALE`;
  a pending conclusion as `G5_EVIDENCE_PENDING`; a non-success conclusion as
  `G5_EVIDENCE_NOT_SUCCESSFUL`.
- Connector evidence gating: incomplete connector evidence is rejected as
  `CONNECTOR_EVIDENCE_INCOMPLETE`.
- Human-observed gating: a label mismatch is rejected as
  `HUMAN_OBSERVED_LABEL_MISMATCH`; a missing attestation as
  `HUMAN_ATTESTATION_MISSING`; a qualified human-observed success as
  `QUALIFIED_HUMAN_OBSERVED_G5_SUCCESS`.
- Fail-closed deterministic input validation: missing identity is rejected as
  `REQUIRED_G5_IDENTITY_MISSING`, invalid SHA binding as
  `INVALID_OR_MISSING_SHA_BINDING`, missing required workflows as
  `REQUIRED_WORKFLOW_EVIDENCE_MISSING`, and invalid observation time as
  `INVALID_G5_OBSERVATION_TIME`.
- Determinism and idempotency: identical inputs yield a stable digest and
  identical decisions; the decision is computed purely in memory with no
  filesystem side effect.
- Every authority field is fixed `False`; verification decisions never grant
  merge, deployment, production, audit, or scale authority.

The exact previous merge SHA bound by this node is SCRUM-370's PR #490
(`566fdf19159b85df59ba1793ae4b22a08b685433`), which is the current `pre-prod`
tip — the dependent rollout (SCRUM-342 … SCRUM-334) must not admit until this
verification passes.

## Guardrails

```text
EXACT_PREVIOUS_MERGE_SHA_IS_BOUND_TO_G5_EVIDENCE_HEAD_SHA.
G5_PUSH_EVENT_AND_MAIN_BRANCH_ARE_REQUIRED_FOR_VERIFICATION.
EXACT_HEAD_SHA_BINDING_IS_REQUIRED_FOR_EVIDENCE.
PREVIOUS_BATCH_G5_VERIFICATION_DOES_NOT_GRANT_TASK_OR_GATE_AUTHORITY.
```

## Wiring

- New node instruction card
  `core/node-architect/node-instructions/scale_control/previous-batch-g5-verification.node-instruction.yaml`
  (validated against `schemas/node-architect/node-instruction.schema.json`;
  authority boundary fixed `False`; the terminal verification gate routes to the
  dependent batch admission with no later node).
- New NA81 test `tests/scale_control/test_previous_batch_g5_verification_na81.py`
  binds the #307 brief to the existing executable
  `node_architect.previous_batch_g5_verification` (imported via an absolute
  `tools/` path insertion so `python -m unittest discover` resolves it from the
  repo root) and validates the closed decision schema. 28 deterministic
  scenarios pass.
- Changelog fragment only; no `*.node.json` `description`/`source` fields edited
  and no registry `source_sha` mutated (provenance-SHA trap avoided).

Parent authority: AR-SCRUM288-RECERT-20260814-R10 (issue #232), task SCRUM-372.
Targets pre-prod only; main is FORBIDDEN.
