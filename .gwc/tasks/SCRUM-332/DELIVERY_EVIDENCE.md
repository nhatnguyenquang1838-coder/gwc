# SCRUM-332 · NA81 Delivery Evidence

- **Task:** SCRUM-332 — `runtime_checkpoint.state-reconciliation`
- **GitHub:** #267 · **Jira:** SCRUM-332 · **Family:** SCRUM-292 · **Epic:** SCRUM-288
- **Route:** `AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN`
- **Parent authority:** `AR-SCRUM288-20260811-R4` (run `SCRUM-288-NA81-20260811-R4`, issue #232)
- **Classification:** `DELTA_REQUIRED` (historical `state_reconciliation.py` = SCRUM-209 is reuse
  evidence only; it lacked three-source reconciliation, deterministic source precedence, and
  explicit UNKNOWN-state / readback-before-retry handling required by the current brief).
- **Predecessors verified:** SCRUM-326/#261 (Done, Hermes) + SCRUM-331/#266 (Done, Hermes)
- **Merge SHA:** `<filled-after-merge>` · **Head SHA:** `<filled-after-push>`

## Classification rationale (why not VERIFIED_REUSE)

The existing `tools/node_architect/runtime_checkpoint/state_reconciliation.py` implements
`reconcile_state` / `classify_drift` for a different (SCRUM-209) contract: it classifies
*drift* (lease/cas/base/head/scope/approval) and routes, but does **not** reconcile three
distinct sources (persisted checkpoint, external readback, canonical state), does **not**
classify outcome as CONFIRMED/PENDING/FAILED/UNKNOWN, and does **not** enforce
`unknown` never completes nor readback-before-retry. The current SCRUM-332 brief requires
exactly those. So a delta was implemented as a backward-compatible extension; no existing
symbol was changed.

## Requirement → Code → Test map (current-task bound)

| # | Current SCRUM-332 requirement (AC/EARS) | Code (this SHA) | Test (this SHA) |
|---|------------------------------------------|-----------------|-----------------|
| 1 | Reconcile persisted checkpoint + external readback + canonical state after interruption | `reconcile_sources(evidence)` reads `canonical_state`, `external_readback`, `persisted_checkpoint` | `test_confirmed_all_agree_resumes`, `test_precedence_*`, `test_all_absent_is_unknown` |
| 2 | Deterministic source precedence (canonical > readback > checkpoint) | `SOURCE_PRECEDENCE`; authoritative-source selection loop | `test_source_precedence_order`, `test_precedence_skips_unknown_canonical_to_readback` |
| 3 | Classify state CONFIRMED/PENDING/FAILED/UNKNOWN | `classify_source_state`, `SourceState` | `test_classify_source_state_maps_aliases` |
| 4 | `unknown` must never be guessed into completion | UNKNOWN → `outcome=FAIL`, never PASS | `test_unknown_never_completes`, `test_all_absent_is_unknown` |
| 5 | Retry / replay requires authoritative external readback first | `readback_ok` gate → else `STOP_BLOCKED`/`READBACK_REQUIRED_BEFORE_RETRY` | `test_readback_required_before_retry`, `test_pending_without_readback_blocked`, `test_precedence_checkpoint_only_blocked_without_readback` |
| 6 | Conflicting / stale checkpoint (fence) handled, not blindly trusted | `conflict` flag; `REPAIR` when readback confirms authoritative | `test_stale_checkpoint_repaired_when_readback_confirms`, `test_pending_with_stale_checkpoint_repairs`, `test_conflicting_readback_blocks` |
| 7 | Deterministic replay (same evidence → identical result) | frozen result + `result_digest` over stable body | `test_deterministic_same_evidence_same_digest` |
| 8 | Never infer success/failure from unknown; never grants authority | `authority_granted=False` always; UNKNOWN/ABSENT → FAIL | `test_invalid_input_does_not_crash`, `test_non_mapping_input_safe`, `test_unknown_never_completes` |
| 9 | Contract schema for the new result | `schemas/state-reconciliation-sources-result.schema.json` | `test_result_schema_accepts_all_routes` |

## Files changed (scoped to this task)

- `tools/node_architect/runtime_checkpoint/state_reconciliation.py` — added `SourceState`,
  `SOURCE_PRECEDENCE`, `classify_source_state`, `SourceReconciliationResult`, `reconcile_sources`
  (backward-compatible; `reconcile_state`/`classify_drift` untouched).
- `tests/test_runtime_checkpoint_state_reconciliation_na81.py` — 18 NA81 acceptance tests.
- `schemas/state-reconciliation-sources-result.schema.json` — result contract.

## Verification commands (run at this SHA)

```bash
# 1. NA81 acceptance tests (no PYTHONPATH — mirrors CI unittest discover)
env -u PYTHONPATH python3 -m unittest discover -s tests -p 'test_runtime_checkpoint_state_reconciliation_na81.py'

# 2. Family (F4) validator for runtime_checkpoint
python3 tools/node_architect/validate_node_catalog_runtime_checkpoint.py

# 3. Existing runtime_checkpoint regression (must stay green)
env -u PYTHONPATH python3 -m unittest tests.test_cas_write_guard_na81 tests.test_cas_write_guard tests.test_checkpoint_persist_na81
```

## Result: 18/18 NA81 tests PASS · F4 validator PASS · 51 existing runtime_checkpoint tests PASS.
