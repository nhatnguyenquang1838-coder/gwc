# SCRUM-275 Implementation Tasks

Ordered task decomposition. Each task is independently testable.

## SUB-TASK-1 — Pre-prod bootstrap + task-branch tool
- Add `create_autonomous_task_branch.py`.
- Implement `bootstrap_preprod(base_main_sha)` (guarded, idempotent) and
  `create_task_branch(run_id, task_id, preprod_sha)` enforcing head pattern and
  rejecting `main` base / force push.
- Depends on: none.

## SUB-TASK-2 — Draft PR assembly with graph/story body
- Add `assemble_autonomous_preprod_pr.py` wrapping `draft_pr_creation`; render the
  PR body via the SCRUM-271 graph/story renderer; forbid `main` base and base
  change.
- Depends on: SUB-TASK-1.

## SUB-TASK-3 — Exact-head G3 readiness validator
- Add `validate_autonomous_g3_readiness.py`: bind base/head/PR-number/draft
  readback/diff digest/CI/review; emit G3 PASS only on exact readback; detect
  head drift.
- Depends on: SUB-TASK-2.

## SUB-TASK-4 — Standing-policy G4 receipt materializer
- Add `materialize_autonomous_g4_receipt.py`: load SCRUM-272 policy; validate
  non-expired, head+scope-bound receipt.
- Depends on: SUB-TASK-3.

## SUB-TASK-5 — Governed pre-prod merge + proof
- Add `merge_autonomous_preprod_pr.py`: squash-merge into `pre-prod` only; write
  `g4/merge-proof.yaml` binding approved head + `pre_prod_merge_sha`.
- Depends on: SUB-TASK-4.

## SUB-TASK-6 — Runtime workflow
- Add `.github/workflows/autonomous-preprod-runtime.yml` wiring the tools.
- Depends on: SUB-TASK-1..5.

## SUB-TASK-7 — Tests
- Add `tests/test_autonomous_preprod_delivery.py` and
  `tests/test_autonomous_preprod_g4_merge.py`; run both plus existing G3/G4
  regressions to confirm green.
- Depends on: SUB-TASK-1..6.

## Execution order
SUB-TASK-1 → SUB-TASK-2 → SUB-TASK-3 → SUB-TASK-4 → SUB-TASK-5 → SUB-TASK-6 → SUB-TASK-7
