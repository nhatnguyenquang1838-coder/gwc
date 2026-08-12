# SCRUM-330 DELIVERY EVIDENCE

**Task:** SCRUM-330 — `runtime_checkpoint.lease-renewal`  
**Brief:** GitHub #265 / Jira SCRUM-330  
**Authority:** AR-SCRUM288-20260811-R4 (issue #232, run `SCRUM-288-NA81-20260811-R4`)  
**Head SHA:** `173a2683`  
**Branch:** `auto/SCRUM-330-na81-20260810`  
**Target:** `pre-prod`

## Requirement → Code → Test map

| Brief requirement | Code change | Test |
|---|---|---|
| Renew only by **same actor/run** (same `run_id` as the active lease). | Added `run_id: str = ""` to `Lease` dataclass; new step **1b** in `evaluate_renewal` rejects mismatched `run_id` or `observed_run_id` with `RUN_ID_MISMATCH`. | `test_valid_renewal_same_run_advances_token` (same run → renewed, token +1) |
| `RUN_ID_MISMATCH` reconciliations fail closed — never rebind execution to a different run. | `RUN_ID_MISMATCH` added to `RECONCILE_REASONS`; evaluated before scope checks. | `test_run_id_mismatch_routes_reconcile`, `test_observed_run_id_mismatch_routes_reconcile` |
| Owner/scope/authority never changed through renewal; preserve lineage. | `renew_lease` copies `run_id` into the renewed lease; owner/task/scope/base/repository are explicitly preserved in the new `Lease`. | `test_renewed_lease_preserves_run_id_lineage` |
| Expired lease renewal fails deterministically (no stale worker). | Unchanged — `_parse_ts` + grace check already rejects expired leases with `LEASE_EXPIRED_NO_GRACE`. Regression verified. | `test_expired_lease_routes_reconcile` |
| Idempotent readback — same inputs produce the same lease identity. | `Lease.to_dict` includes `run_id`; `_lease_digest` produces a stable digest. | `test_idempotent_renewal_readback`, `test_deterministic_digest_same_inputs` |
| `run_id` is part of the digest (not silently dropped). | `Lease.to_dict` adds `"run_id": self.run_id` so the canonical digest reflects it. | `test_run_id_is_part_of_lease_digest` |
| No regression: owner mismatch still routes to reconcile. | Unchanged `OWNER_MISMATCH` path (step 1). | `test_owner_mismatch_routes_reconcile` |
| Backward compatibility: legacy leases without `run_id` still renew. | `run_id`/`observed_run_id` are optional (`None`); `_validate_binding` unchanged; `Lease.run_id` defaults to `""`. | `test_legacy_lease_without_run_id_still_renews` |

## Verified deliverables
- **Code:** `tools/node_architect/lease_renewal.py` — NA81 run binding delta (backward-compatible).
- **Tests:** `tests/test_lease_renewal_na81.py` — 11 current-task tests (sys.path[0] fix applied).
- **Old tests:** `tests/test_lease_renewal.py` — 14 regression tests green.

## Verification commands
```bash
# Unit tests (old + new, no PYTHONPATH required)
python3 -m unittest discover -s tests -p 'test_lease_renewal*.py'

# Runtime-checkpoint family validator
python3 tools/node_architect/validate_node_catalog_runtime_checkpoint.py
```

## Results
```text
Ran 25 tests in 0.001s — OK
PASS runtime_checkpoint node catalog
```
