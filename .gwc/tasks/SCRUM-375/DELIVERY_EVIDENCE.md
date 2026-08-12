# SCRUM-375 (#310) · scale_control.workflow-run-observability — Delivery Evidence

**Route:** `AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN`
**Parent authority:** `AR-SCRUM288-20260811-R4` (issue #232, `github-actions[bot]`)
**Working branch:** `auto/SCRUM-375-na81-20260810` (manifest-fixed date `20260810`)
**Base SHA at claim:** `e18087989e56338776105831c2693dc64087c489` (live `pre-prod`)
**Classification:** DELTA_REQUIRED — module logic reused; current-task evidence map delivered as `*_na81.py` tests.

## Why not VERIFIED_REUSE
The existing decision module `tools/node_architect/workflow_run_observability.py`
already implements the classification logic, BUT the brief's *No auto-close rule*
("Done requires SCRUM-375/#310-bound exact-SHA observability evidence") was not
satisfied: no test bound the exact brief scenarios (exact-SHA terminal, genuine
non-terminal, terminal failure, empty/unsupported lookup, stale/adjacent run,
fallback, replay) to the exact module on the exact SHA. That bound evidence map
is the DELTA delivered here.

## DAG (live `issuelinks`, authoritative per §3)
- `inwardIssue` (predecessor): **SCRUM-376** — status Done ✓ (only predecessor)
- `outwardIssue` (consumers): SCRUM-374, SCRUM-321 (blocked BY 375)
- Descriptor-prose "predecessors SCRUM-374+SCRUM-321" is text drift; live links win.

## Requirement → Code → Test map
| Brief requirement (family invariants) | Code (exact module) | Test (`tests/test_workflow_run_observability_na81.py`) |
|---|---|---|
| Exact-SHA terminal run → SUCCESS | `decide_workflow_run_observability` selects exact `head_sha` runs; all success → SUCCESS | `test_exact_sha_terminal_run_is_success` |
| Real non-terminal run → CI_PENDING (not SUCCESS) | `pending_workflow_names` → `CI_PENDING` | `test_genuine_non_terminal_run_is_ci_pending` |
| Terminal failure → CI_FAILED | `failed_workflow_names` → `CI_FAILED` | `test_terminal_failure_is_ci_failed` |
| Empty/unsupported lookup → OBSERVABILITY_INCOMPLETE, not CI_PENDING | `CONNECTOR_OBSERVABILITY_INCOMPLETE` (ERROR/UNSUPPORTED) / `RUNS_MISSING` (EMPTY+filtered, not CI_PENDING) | `test_empty_filtered_lookup_is_not_ci_pending`, `test_unsupported_connector_view_is_observability_incomplete`, `test_error_connector_is_observability_incomplete` |
| Stale/adjacent runs are invalid evidence | non-exact `head_sha` runs excluded from `selected`; `mismatched_run_count` incremented | `test_stale_adjacent_run_is_invalid_evidence_and_excluded` |
| Supported fallback resolves exact → SUCCESS | `exact_filter_applied=True` + exact runs → SUCCESS | `test_fallback_success_when_connector_filter_resolves_exact` |
| Replay determinism (exact-SHA evidence reproducible) | `decision_digest` stable for identical input | `test_replay_is_deterministic` |
| SCALE_CONTROL_EVIDENCE_DOES_NOT_GRANT_SCALE_AUTHORITY | all `*_authority_granted=False`, `read_only_projection=True` | `test_observability_evidence_grants_no_scale_authority` |

## Files changed
- `tests/test_workflow_run_observability_na81.py` — NEW (10 tests, SCRUM-375-bound)
- `.gwc/tasks/SCRUM-375/DELIVERY_EVIDENCE.md` — this evidence map

## Verification commands (run from repo root, NO PYTHONPATH — CI style)
```
python -m unittest tests.test_workflow_run_observability_na81 -v
python -m unittest tests.test_scale_control_m4_batch_b2 -v   # backward-compat, must stay green
python tools/node_architect/validate_node_catalog_scale_control.py
```
All PASS locally. CI gate `validate` + `parent-authority-required` must PASS on exact merge SHA.

## G5 readback
After squash-merge to `pre-prod`, verify exact files on exact merge SHA via
`git show <merge_sha>:tools/node_architect/workflow_run_observability.py` and
`git show <merge_sha>:tests/test_workflow_run_observability_na81.py`.
