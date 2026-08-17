# SCRUM-319 diff-readback DELTA_REQUIRED (NA81-F3-N04)

- Task: `repo_delivery.diff-readback` (#254) — implement complete, fail-closed diff readback.
- Route: `AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN`; exact base `pre-prod@08a72eede1485332f88e0f51f35cfa3aa6d054fe`.
- Authority: `AR-SCRUM288-RECERT-20260814-R10` (receipt #5288357997); `controller_decision: DELTA_REQUIRED` (Controller CORRECTION seq=3, overturning prior VERIFIED_REUSE).
- Predecessor `SCRUM-318/#253` (Done) closed; consumers SCRUM-320/#255, SCRUM-322/#257, SCRUM-334/#269, SCRUM-364/#299. Historical SCRUM-196 = evidence only.

## Delta (minimum source-of-truth, authorized paths only)
- `tools/node_architect/diff_readback.py`: close the three live-AC gaps without changing the closed decision schema or breaking legacy callers:
  - **Completeness/visibility fail-closed**: new optional `readback_coverage` (`complete`|`partial`|`unknown`); `partial`→`INCOMPLETE_VISIBILITY`, `unknown`/other→`READBACK_VISIBILITY_UNKNOWN`. Absent ⇒ legacy lenient (preserves existing tests).
  - **Explicit prohibited-change detection**: new optional `prohibited_paths`; any matching changed file ⇒ `PROHIBITED_CHANGE_DETECTED` (distinct from `OUT_OF_SCOPE_PATH`). Targets immutable authority/control-plane paths.
  - **Stale SHA fail-closed**: new optional `expected_base_sha`/`expected_head_sha`; mismatch ⇒ `STALE_BASE_SHA`/`STALE_HEAD_SHA`.
  - **Deterministic content/provenance evidence**: `decision_digest` now fingerprints repository, base/head, coverage, sorted paths, prohibited hits, reason codes and outcome ⇒ replay-stable and content-aware (same input ⇒ same digest).
  - **No authority grant**: `merge/deployment/production_authority_granted` remain `const false`.
- `tests/test_repo_delivery_scrum319_diff_readback_delta.py` (new): Jira AC matrix — complete diff, incomplete visibility, foreign/out-of-scope, prohibited path/change, stale base/head SHA, same-input replay/digest stability, no authority grant.
- No schema mutation (closed `diff-readback-decision.schema.json` unchanged; new reason codes are free-form strings). No instruction/route wiring change (already present at base via SCRUM-317 #466).

## Validation
- `python3 tools/node_architect/validate_node_catalog_repo_delivery.py` → `REPO_DELIVERY_NODE_CATALOG_VALID`.
- `pytest tests/test_repo_delivery_scrum319_diff_readback_delta.py tests/test_repo_delivery_m5_batch_b2.py tests/test_node_catalog_repo_delivery.py ...` → all green (legacy verdicts preserved).
