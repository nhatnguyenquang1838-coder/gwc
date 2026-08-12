# SCRUM-366 · failure_recovery.lease-expiry-recovery — Delivery Evidence (NA81)

- **Route:** `AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN`
- **Parent receipt:** `AR-SCRUM288-20260811-R4` (issue #232, run `SCRUM-288-NA81-20260811-R4`)
- **Branch:** `auto/SCRUM-366-na81-20260810` → `pre-prod`
- **Classification:** `DELTA_REQUIRED` (historical SCRUM-243 module existed but lacked current-actor/run/scope binding + renewal-race fencing)
- **Predecessors verified Done:** SCRUM-329 (#264), SCRUM-330 (#265)

## Current-task requirement → code → test map

| Brief requirement (SCRUM-366) | Code location | Test |
|---|---|---|
| Fence expired lease holder; never continue stale holder | `decide_lease_expiry_recovery` → `FENCE_STALE_WORKER` when `worker_fencing_token < observed_fencing_token` | `test_stale_holder_fenced` |
| Reconcile unknown in-flight effect before reacquire (no blind retry) | `side_effect_status in {COMMITTED,UNKNOWN,PENDING}` → `RECONCILE`, `blind_retry_allowed=False` | `test_unknown_in_flight_effect_reconciles`, `test_committed_in_flight_effect_reconciles` |
| Permit reacquire/resume **only by current authorized actor/run/scope** | new params `expected_actor_id/expected_run_id/expected_scope_hash` + `_binding_violation` → `FENCE_WRONG_ACTOR/RUN/SCOPE` | `test_wrong_actor_fenced`, `test_wrong_run_fenced`, `test_wrong_scope_fenced`, `test_wrong_actor_during_valid_lease_also_fenced` |
| Renewal race / concurrent reacquire fenced | new param `concurrent_reacquire_detected` → `FENCE_CONCURRENT_REACQUIRE` | `test_renewal_race_fenced` |
| Exact expiry boundary | `lease_expired = now_epoch_ms >= lease_expires_epoch_ms` | `test_exact_boundary_now_equal_expires_is_expired`, `test_one_ms_before_boundary_still_valid` |
| Never expand scope/authority (family invariant) | fenced outcomes never set `advancement_allowed`/`side_effect_allowed` | `test_wrong_actor_fenced` etc. |
| Duplicate/concurrent agent fenced | `duplicate_agent_detected` → `FENCE_DUPLICATE_AGENT` | `test_duplicate_agent_race_fenced` |
| Deterministic replay / revision digest | `is_replay_equivalent` ignores `observed_at`+`decision_digest`; `decision_digest` over stable fields | `test_replay_equivalent_ignores_observation_time`, `test_replay_differs_on_wrong_actor_decision` |
| Backward compatible (historical M5 callers keep working) | new params default `None`/`False`; unbound call keeps `CONTINUE_AFTER_REACQUIRE` | `test_unbound_call_keeps_historical_resume` |

## Files changed (this branch)
- `tools/node_architect/lease_expiry_recovery.py` — added actor/run/scope binding + renewal-race fencing (backward compatible)
- `tests/test_lease_expiry_recovery_na81.py` — 15 new NA81 tests (imports `node_architect` via `sys.path[0]` insert, SCRUM-323 lesson)

## Verification commands (exact-head)
```
python3 -m unittest discover -s tests -p 'test_lease_expiry_recovery_na81.py'   # 15 passed
python3 -m unittest tests.test_lease_expiry_recovery                            # 8 passed (M5 compat)
python3 tools/node_architect/validate_node_catalog_failure_recovery.py         # PASS
```

## Standalone decision proof
```
$ python3 -c "from tools.node_architect.lease_expiry_recovery import decide_lease_expiry_recovery as d; \
  print(d(task_id='SCRUM-366',repository='nhatnguyenquang1838-coder/gwc',branch='auto/SCRUM-366-na81-20260810',\
  base_sha='ba018a8be718be1137a875ffe2533520a6209613',head_sha='$(git rev-parse HEAD)',scope_hash='sha256:60a28922c6921e4f000000000000000000000000000000000000000000000000',\
  lease_id='lease-1',worker_id='worker-b',run_id='run-1',now_epoch_ms=2000,lease_expires_epoch_ms=1000,\
  observed_fencing_token=7,worker_fencing_token=7,readback_status='VERIFIED_ZERO_EFFECT',\
  reacquire_status='REACQUIRED_MONOTONIC',duplicate_agent_detected=False,side_effect_status='NONE',\
  expected_actor_id='worker-a',expected_run_id='run-1',expected_scope_hash='sha256:60a28922c6921e4f000000000000000000000000000000000000000000000000')['outcome'])"
FENCE_WRONG_ACTOR
```
