# SCRUM-363 Delivery Evidence — failure_recovery.stale-session-reconciliation

- **Task:** SCRUM-363 · GitHub #298 · Family SCRUM-296 (failure_recovery) · Epic SCRUM-288
- **Route:** AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN
- **Branch:** auto/SCRUM-363-na81-20260810 (manifest date 20260810)
- **Parent authority:** AR-SCRUM288-20260811-R4 (issue #232, github-actions[bot])
- **Classification:** DELTA_REQUIRED (existing `stale_session_reconciliation.py` lacked "stale base/head" detection and explicit "safe rebind" guidance from the current brief)
- **Base SHA:** b3480ddffcae74ba8428dde914244fca810b5be3 (origin/pre-prod)
- **Merge SHA:** recorded in Jira delivery comment after G5 readback

## Current-task requirement → code → test map (brief: "Test stale base/head, expired/wrong lease, stale checkpoint, foreign dirty files, conflicting session, safe rebind and replay")

| Brief requirement | Code (tools/node_architect/stale_session_reconciliation.py) | Test (tests/test_stale_session_reconciliation_na81.py) |
|---|---|---|
| stale base/head | `stale_base`/`stale_head` from observed vs canonical base/head sha → SUPERSEDE | test_stale_base_supersedes, test_stale_head_supersedes, test_current_base_head_continues |
| expired/wrong lease | `lease_status in {EXPIRED,MISSING}` → SUPERSEDE | test_expired_lease_supersedes, test_missing_lease_supersedes |
| stale checkpoint | `observed_checkpoint_rev < canonical_checkpoint_rev` → SUPERSEDE | test_stale_checkpoint_supersedes |
| foreign dirty files | `working_tree_status!=CLEAN` → RECONCILE(WORKING_TREE_NOT_CLEAN) | test_foreign_dirty_files_reconcile |
| conflicting session | foreign `observed_owner` → SUPERSEDE + rebind_to_canonical | test_conflicting_session_supersedes |
| safe rebind | `rebind_to_canonical=True` only on SUPERSEDE | test_safe_rebind_allowed_only_on_supersede |
| replay | `is_replay_equivalent()` ignores observed_at | test_replay_equivalent_ignores_observation_time |

## Backward compatibility
- New optional params `observed_base_sha`/`canonical_base_sha`/`observed_head_sha`/`canonical_head_sha` (default None → no behavior change when omitted).
- New additive decision fields `stale_base`, `stale_head`, `rebind_to_canonical` (no existing test asserts their absence).
- Existing `tests/test_stale_session_reconciliation.py` (task_id SCRUM-240) still green.

## Verification commands (run from repo root, no PYTHONPATH)
```
python -m unittest tests.test_stale_session_reconciliation_na81 tests.test_stale_session_reconciliation
python tools/node_architect/validate_node_catalog_failure_recovery.py
python -m unittest discover -s tests -p "test_*na81.py"
```
All pass on the delivered head.
