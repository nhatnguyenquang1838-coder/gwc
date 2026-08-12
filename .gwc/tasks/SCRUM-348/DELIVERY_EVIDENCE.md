# SCRUM-348 Delivery Evidence

## Task
**SCRUM-348** · `sync_projection.projection-reconcile-readback` · GitHub #283 · Jira SCRUM-348
Lane: SCRUM-288 (NA81) · Parent receipt: AR-SCRUM288-20260811-R4

## Classification
**DELTA_REQUIRED**

## Requirements (current NA81 brief)
1. Reconcile intended projection state with authoritative external readback using source revision + idempotency identity.
2. Return deterministic `CONFIRMED`, `PENDING`, `CONFLICT` or `UNAVAILABLE`; unknown outcome is never inferred success and must be read back before any repeat attempt.
3. Preserve backward compatibility with existing M4 callers/tests that do not supply the new parameters.
4. Maintain read-only projection boundary; never grant write/approval/merge/deployment/production authority.

## Code → Test Evidence Map

| Requirement | Code Location | Test(s) |
|-------------|---------------|---------|
| CONFIRMED when readback confirms expected state | `tools/node_architect/projection_reconcile_readback.py` : `elif use_new_contract:` → `proj_state == prior_state` branch | `test_confirmed_when_states_match` |
| PENDING when no prior readback / unknown state | same file : `elif not isinstance(prior_readback, dict):` and `if proj_state is None or prior_state is None:` | `test_pending_when_no_prior_readback` |
| CONFLICT when readback diverges | same file : `elif proj_state != prior_state:` | `test_conflict_when_states_diverge` |
| UNAVAILABLE when gates blocked or input invalid | same file : `if reason_codes:` branch inside `use_new_contract` | `test_unavailable_when_gates_blocked` |
| Unknown never inferred success | same file : missing canonical_state routes to PENDING/UNAVAILABLE, never CONFIRMED | `test_unknown_never_inferred_success` |
| Backward-compatible READY/BLOCKED preserved | same file : `else:` legacy branch | existing `tests/test_reconcile_readback_m4_batch_b3.py` (9 tests PASS) |
| Schema closed-object + authority consts validated | `schemas/projection-reconcile-readback.schema.json` | `jsonschema` validation in all NA81 + old tests |
| Family runtime binding validated | `tools/node_architect/validate_node_catalog_sync_projection.py` | validator PASS |

## Verification Commands (exact SHA `d5b266d8e0d4b753a58ab8544b2e80790113c594`)
```bash
cd /Users/mac/prj/gwc-wt-SCRUM-348
python tools/node_architect/validate_node_catalog_sync_projection.py --root .
python -m unittest tests.test_reconcile_readback_m4_batch_b3
python -m unittest tests.sync_projection.test_projection_reconcile_readback_na81
```

## Scope Hash
`sha256:60a28922c6921e4fe6172aebef5a10a48f419427da132dc3e41f60c0856bcfa3` (R4 manifest)
