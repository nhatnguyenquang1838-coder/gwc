# SCRUM-369 Delivery Evidence
**Task:** SCRUM-369 (`failure_recovery.version-drift-rollback-routing`) · GitHub #304 · NA81-F8-N09
**Route:** `AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN`
**Parent receipt:** `AR-SCRUM288-20260811-R4`
**Head branch:** `auto/SCRUM-369-na81-20260810`

## Classification
`DELTA_REQUIRED` — historical SCRUM-246/PR #XXX implementation
lacked: unavailable-version-evidence blocking and explicit no-destructive-effect test.
Historical reuse evidence is explicitly NOT current-task delivery proof.

## Requirement → Code → Test Evidence Map

| # | Current SCRUM-369 brief requirement | Code change (exact symbol) | Test coverage |
|---|---|---|---|
| 1 | Compatible continuation | existing `compatibility_rule="COMPATIBLE"` → `CONTINUE_COMPATIBLE` | existing `test_compatible_drift_continues_with_evidence` |
| 2 | Replan/rebind | existing `NEW_EPOCH_REQUIRED` → `ROUTE_NEW_EPOCH` | existing `test_new_epoch_route` |
| 3 | Rollback recommendation | existing `ROLLBACK_REQUIRED` → `ROUTE_ROLLBACK_EVIDENCE` | existing `test_rollback_route_preserves_evidence_without_deploy_authority` |
| 4 | Blocked/human-required | existing `UNKNOWN` → `BLOCK_UNSUPPORTED_DRIFT` | NA81 `test_blocked_human_required_route` |
| 5 | Unavailable version evidence BLOCKS | new `version_evidence_unavailable` check + `VERSION_EVIDENCE_UNAVAILABLE` | NA81 `test_version_evidence_unavailable_blocks` + `test_version_evidence_unavailable_both_missing` |
| 6 | No destructive effect for rollback | rollback decision carries `g5_manual_action_authorized=False`, no destructive flag | NA81 `test_rollback_route_has_no_destructive_effect` |
| 7 | Stale replay rejected before rollback | existing stale replay check | existing `test_stale_replay_rejected_before_rollback` |
| 8 | Deterministic replay | `decision_digest` bound to canonical payload | NA81 `test_deterministic_replay_same_digest` |
| 9 | Backward-compatible extension | new params defaulted; existing 16 M5 tests still pass | existing 16 M5 tests + NA81 8 tests = 24 OK |
| 10 | F8 family + catalog validity | no node / package / matrix changes | `validate_node_catalog_failure_recovery.py` → PASS |

## Verification Commands
```bash
PYTHONPATH=. python -m unittest tests.test_failure_recovery_m5_batch tests.test_version_drift_rollback_routing_na81 -v
PYTHONPATH=. python tools/node_architect/validate_node_catalog_failure_recovery.py
```

## Result
- 24/24 unit tests pass (16 existing + 8 NA81)
- F8 validator PASS
- Schema `version-drift-rollback-routing-decision.schema.json` unchanged (additionalProperties:true)

## DAG Drift Note
Live Jira `issuelinks` for SCRUM-369 show zero `inwardIssue` blockers (unblocked).
The Jira brief states predecessors SCRUM-317 + SCRUM-332, but live links are
reversed (317 and 332 are blocked BY 369, not vice versa). Readiness computed
from live `inwardIssue`; claim proceeded per prompt DAG-drift rule.

## Exclusions
No deploy/release/scale/runtime/credential/migration/main-merge operations.
Child PR targets `pre-prod` only. Human G4 remains mandatory for `pre-prod -> main`.
