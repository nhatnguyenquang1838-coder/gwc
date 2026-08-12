# SCRUM-347 Delivery Evidence

## Current-task requirement → code → test map

| # | Current requirement (NA81 brief) | Code location | Test(s) |
|---|----------------------------------|---------------|---------|
| 1 | Classify `NO_DRIFT`, material drift, conflict, unavailable readback | `tools/node_architect/projection_drift_detection.py`: `detect_projection_drift` (lines 115–165) | `test_no_drift_with_readback_meta`, `test_material_drift`, `test_conflicting_target_state`, `test_unavailable_readback` |
| 2 | Stale / out-of-order readback detection | `tools/node_architect/projection_drift_detection.py`: `readback_meta={"stale": ...}` branch (lines 115–121) | `test_stale_readback`, `test_stale_readback_precedence_over_drift` |
| 3 | Conflicting target state detection | `tools/node_architect/projection_drift_detection.py`: `readback_meta={"conflict": ...}` branch (lines 122–124) | `test_conflicting_target_state` |
| 4 | Unavailable readback detection | `tools/node_architect/projection_drift_detection.py`: `readback_meta={"unavailable": ...}` branch (lines 125–127) | `test_unavailable_readback` |
| 5 | Deterministic digest / replay with readback meta | `tools/node_architect/projection_drift_detection.py`: `digest_payload` includes `observed_at` + `reason_code` (lines 165–173) | `test_deterministic_digest_with_readback_meta`, `test_replay_same_result` |
| 6 | No back-write authority | `tools/node_architect/projection_drift_detection.py`: `read_only_projection=True`, all `*_authority_granted=False` (lines 188–194) | `test_no_back_write_authority` |
| 7 | Backward-compat M4 interface | `tools/node_architect/projection_drift_detection.py`: `readback_meta=None` default preserves original outcome/reason_code logic | `tests/test_drift_detection_m4_batch_b3` (11 tests, all PASS) |

## Verification commands (exact SHA at merge time)

```bash
cd /Users/mac/prj/gwc-wt-SCRUM-347
PYTHONPATH=tools python3 -m unittest tests.test_projection_drift_detection_na81 tests.test_drift_detection_m4_batch_b3 -v
python3 tools/node_architect/validate_node_catalog_sync_projection.py
python3 -m unittest discover -s tests -p "test_*projection*" -v
```

## Classification rationale

Existing `projection_drift_detection.py` (SCRUM-224) satisfied the original M4 brief but
lacked:
- `observed_at` population
- distinct readback classifications (`stale` / `conflict` / `unavailable`)
- explicit `NO_DRIFT` / `MATERIAL_DRIFT` reason codes for NA81
- digest stability tied to readback signals

→ DELTA_REQUIRED. Backward-compatible extension via optional `readback_meta` parameter.
