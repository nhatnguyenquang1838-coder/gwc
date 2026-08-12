# SCRUM-361 Delivery Evidence — failure_recovery.timeout-recovery

- **Task:** SCRUM-361 · GitHub #296 · Family SCRUM-296 (failure_recovery) · Epic SCRUM-288
- **Route:** AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN
- **Branch:** auto/SCRUM-361-na81-20260810 (manifest date 20260810)
- **Parent authority:** AR-SCRUM288-20260811-R4 (issue #232, github-actions[bot])
- **Classification:** DELTA_REQUIRED (existing `timeout_recovery.py` lacked "real pending" and "interruption" handling from the current brief)
- **Base SHA:** b3480ddffcae74ba8428dde914244fca810b5be3 (origin/pre-prod)
- **Merge SHA:** recorded in Jira delivery comment after G5 readback

## Current-task requirement → code → test map (brief: "Tests: timeout with zero effect, unknown effect, real pending, unavailable readback, retryable/exhausted retry, interruption and replay/no duplicate effect")

| Brief requirement | Code (tools/node_architect/timeout_recovery.py) | Test (tests/test_timeout_recovery_na81.py) |
|---|---|---|
| zero effect (retryable/exhausted) | `effect_status=="ZERO_EFFECT"` → BOUNDED_RETRY / FAIL(RETRY_BUDGET_EXHAUSTED) | test_retryable_has_budget, test_exhausted_retry_fails |
| unknown effect | `effect_status=="UNKNOWN"` → RECONCILE(UNKNOWN_EXTERNAL_EFFECT) | test_unknown_effect_reconciles |
| real pending (distinct from timeout/terminal) | `effect_status=="PENDING"` → WAIT(REAL_PENDING_AWAIT_READBACK) | test_real_pending_routes_to_wait_not_reconcile |
| unavailable readback | `readback_status!="VERIFIED"` → RECONCILE(READBACK_NOT_VERIFIED) | test_unavailable_readback_reconciles |
| interruption (no duplicate effect) | `interruption_detected` + would-retry/poll → RECONCILE(INTERRUPTION_REQUIRES_RECHECK) | test_interruption_blocks_bounded_retry, test_interruption_blocks_pending_poll, test_interruption_keeps_confirmed_failure |
| replay / no duplicate effect | `is_replay_equivalent()` ignores observed_at | test_replay_equivalent_ignores_observation_time, test_distinct_decisions_are_not_replay_equivalent |

## Backward compatibility
- New param `interruption_detected: bool = False` (default off → prior behavior unchanged).
- New `effect_status=="PENDING"` value routes to WAIT (previously fell through to RECONCILE UNSUPPORTED).
- Existing `tests/test_timeout_recovery.py` (task_id SCRUM-238) still green.

## Verification commands (run from repo root, no PYTHONPATH)
```
python -m unittest tests.test_timeout_recovery_na81 tests.test_timeout_recovery
python tools/node_architect/validate_node_catalog_failure_recovery.py
python -m unittest discover -s tests -p "test_*na81.py"
```
All pass on the delivered head.
