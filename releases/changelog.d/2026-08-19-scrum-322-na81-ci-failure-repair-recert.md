# SCRUM-322 — NA81 R10 ci-failure-repair current-brief proof

## Type

```text
validation
```

## Delivery classification

`VERIFIED_REUSE` against the live SCRUM-322 brief. The executable implementation
already exists on `pre-prod`; this R10 recovery adds current-task proof only and
does not modify production logic.

## Authority / binding

- Route: `AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN`
- Authority: `AR-SCRUM288-RECERT-20260814-R10`
- Task scope hash: `sha256:466575da49410ce60a83b6ae760c5ae212d88b95998ee2cb27c080a17210fdd2`
- Canonical branch: `auto/SCRUM-322-na81-recert-20260814-r10`
- Execution base: `pre-prod@566fdf19159b85df59ba1793ae4b22a08b685433`
- Predecessor merge evidence: SCRUM-319 PR #469, SCRUM-321 PR #471

## Current brief → code → test proof

| Requirement | Existing executable | Current-task proof |
|---|---|---|
| Repo-fixable exact-head failures classify to bounded repair | `tools/node_architect/ci_failure_repair.py::classify_ci_failure` | `test_repo_fixable_inside_scope` |
| External failure stops typed/fail-closed | `_EXTERNAL_PATTERNS` + classifier | `test_external_failure_blocked_typed` |
| Unknown failure fails closed | `_classify_failure` default | `test_unknown_failure_fails_closed` |
| Missing approved scope cannot authorize repair | scope guard in `classify_ci_failure` | `test_missing_approved_scope_blocked` |
| Repair invalidates old head evidence | `invalidate_prior_head_evidence` | `test_new_head_invalidates_prior_evidence` |
| Classifier never performs repair/merge | `execution_performed=False` | `test_classification_performs_no_execution`, `test_no_merge_authority_ever` |
| Replay conflict/idempotency are explicit | `replay_status` | `test_replay_conflict_detected`, `test_replay_idempotent_for_new_key` |

Legacy PR #444 is not reused as an integration candidate because its branch/base
belongs to R4 and its `.gwc/tasks/SCRUM-322/**` evidence path is outside the R10
authorized path set. This recovery intentionally contains only R10-allowed
`tests/**` and `releases/changelog.d/**` artifacts.

No `main` merge, deploy, release, production data/configuration, secret,
credential, migration, force-push, branch deletion, or authority-plane mutation
is authorized by this delivery.
