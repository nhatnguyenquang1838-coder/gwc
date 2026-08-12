# SCRUM-357 Delivery Evidence

## Current-task requirement → code → test evidence map

| # | Current requirement (NA81 brief) | Code location | Test(s) |
|---|----------------------------------|---------------|---------|
| 1 | Deterministic generation | `tools/node_architect/package_export/export_manifest_generation.py`: `compute_plan_digest`, `compute_manifest_digest`, `_build_manifest_dict` | `test_deterministic_generation` |
| 2 | Missing source/provenance blocks generation | `tools/node_architect/package_export/export_manifest_generation.py`: required source → `MANIFEST_SOURCE_MISSING`, FAIL | `test_required_source_missing_blocks` |
| 3 | Ordering stability | `tools/node_architect/package_export/export_manifest_generation.py`: `compute_plan_digest` sorts by (target, source) | `test_ordering_stable` |
| 4 | Duplicate / extra entry handling | `tools/node_architect/package_export/export_manifest_generation.py`: plan entries processed in deterministic sort order; duplicate source/target produces duplicate evidence records deterministically | `test_duplicate_plan_entry_handled_deterministically` |
| 5 | Source drift (cross-check mismatch) | `tools/node_architect/package_export/export_manifest_generation.py`: `cross_check=True` → `MANIFEST_DIGEST_MISMATCH` | `test_source_drift_mismatch_blocks` |
| 6 | Replay / digest stability | `tools/node_architect/package_export/export_manifest_generation.py`: `existing_manifest` replay → `MANIFEST_IDEMPOTENT_REPLAY`; `compute_manifest_digest` self-consistent | `test_replay_digest_stable` |
| 7 | Authority never granted | `tools/node_architect/package_export/export_manifest_generation.py`: `authority_granted()` always False | `test_authority_never_granted` |

## Classification rationale

Existing `export_manifest_generation.py` (SCRUM-234) satisfies the current SCRUM-357 brief:
- closed deterministic manifest with exact source/target bindings
- provenance via source_digest, target_digest, source_sha, idempotency_key
- missing required source/provenance blocks with `MANIFEST_SOURCE_MISSING`
- ordering, cross-check drift, replay/digest stability all covered by existing implementation and tests

→ VERIFIED_REUSE. DELTA_REQUIRED was ruled out because no current requirement is unmet.

## Verification commands (exact SHA at merge time)

```bash
cd /Users/mac/prj/gwc-wt-SCRUM-357
PYTHONPATH=tools python3 -m unittest tests.package_export.test_export_manifest_generation_na81 -v
```
