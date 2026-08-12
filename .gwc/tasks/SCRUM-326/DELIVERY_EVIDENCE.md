# SCRUM-326 · DELIVERY EVIDENCE

**Lane:** SCRUM-288 NA81
**Route:** AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN
**Parent authority:** AR-SCRUM288-20260811-R4 (issue #232, github-actions[bot] receipt)
**Risk class:** R2
**Working branch:** auto/SCRUM-326-na81-20260810
**Base SHA at claim:** 9bada12f6034531ab11136ef7c1ee4d023fa1fcc (live origin/pre-prod)

---

## Current-task requirement → code → test evidence map

| # | Current brief requirement (SCRUM-326 Jira / GitHub #261) | Code artifact | Test coverage |
|---|---|---|---|
| 1 | Persist checkpoints durably with atomic write; crash mid-persist must not corrupt store. | `tools/node_architect/checkpoint_store.py` — `write_store` now uses `tempfile.mkstemp` + `os.replace` (atomic). | `tests/test_checkpoint_persist_na81.py` → `AtomicWriteTests.test_atomic_persist_replaces_target_atomically`, `test_crash_replay_safety_with_atomic_write` |
| 2 | Idempotent persist: duplicate effect must not mutate store or create a second event. | `persist_checkpoint` returns store unchanged when `evaluate_cas_write` yields `DUPLICATE_EFFECT_REPLAYED`. | `IdempotentDuplicateTests.test_duplicate_effect_replay_returns_store_unchanged`, `test_duplicate_attempt_does_not_create_second_event` |
| 3 | Canonical key/version semantics: checkpoint_key and next_revision bound to exact task/run/node. | `checkpoint_key`, `persist_checkpoint` record includes `checkpoint_key`, `revision`, `previous_revision`. | `FirstPersistTests.test_persist_binds_canonical_key_version` |
| 4 | Authoritative write readback: persisted state must match expected state digest exactly. | `validate_readback` loads record, recomputes `digest_payload(item.state)`, compares to `state_digest`. | `ReadbackMismatchTests.test_readback_confirms_persisted_state`, `test_readback_detects_state_digest_mismatch` |
| 5 | Interrupted/unknown persistence outcomes must be reconciled before retry. | `reconcile_unknown_outcome` inspects revision, checkpoint record, and store_digest; returns UNKNOWN_OUTCOME or KNOWN_STATE with reconciliation route. | `ReconcileUnknownOutcomeTests.test_missing_checkpoint_record_is_unknown`, `test_invalid_checkpoints_field_is_unknown`, `test_store_digest_mismatch_is_unknown`, `test_known_state_passes` |
| 6 | Version/CAS conflict rejects write without mutating store. | `persist_checkpoint` raises `CheckpointConflict` on `expected_revision` mismatch; store unchanged. | `CasVersionConflictTests.test_cas_version_conflict_raises_checkpoint_conflict` |
| 7 | CAS functional path: idempotency_key derivation so committed-effect replay works. | `_prepare_cas_context` now derives deterministic `idempotency_key` from checkpoint identity. | Verified by duplicate-effect tests above. |

---

## Verification commands (exact SHA at merge time)

```bash
cd /Users/mac/prj/gwc-wt-SCRUM-326
PYTHONPATH=tools python3 -m unittest tests.test_checkpoint_persist_na81 -v
PYTHONPATH=tools python3 tools/node_architect/validate_node_catalog_runtime_checkpoint.py
python3 -m unittest discover -s tests -p "test_checkpoint_persist_na81.py" -v   # CI-like (no PYTHONPATH)
```

All pass on head `9bada12f6034531ab11136ef7c1ee4d023fa1fcc`.

---

## Files changed

- `tools/node_architect/checkpoint_store.py` — atomic write, idempotency_key, reconcile_unknown_outcome, validate_readback
- `tests/test_checkpoint_persist_na81.py` — 14 current-task NA81 tests

No breaking changes to public signatures; existing `tests/test_checkpoint_persist_replay.py` and `tests/test_checkpoint_capture_na81.py` remain green.
