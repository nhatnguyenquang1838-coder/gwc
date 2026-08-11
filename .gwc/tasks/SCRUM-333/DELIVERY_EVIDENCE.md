# SCRUM-333 DELIVERY_EVIDENCE

## Requirement → Code → Test Evidence Map (exact head on branch `auto/SCRUM-333-na81-20260810`)

### Current brief (Jira SCRUM-333 + GitHub #268)

| Requirement | Evidence |
|---|---|
| Clean ONLY disposable expired checkpoint hints/interrupt frames | `tools/node_architect/checkpoint_expiry_cleanup.py::classify_entry()` + `plan_cleanup()` |
| Preserve canonical runtime, governance, audit, approval, CI, PR, merge evidence | `PROTECTED_CANONICAL_TYPES` frozenset; `RETAIN_CANONICAL` disposition; `retained_canonical_evidence` in result |
| Ambiguous/mislabeled artifact → fail-closed (retain, never delete) | `classify_entry` checks `PROTECTED_CANONICAL_TYPES` before retention_class |
| Deterministic, idempotent, replay-safe | `plan_cleanup` + `is_replay_equivalent`; `cleanup_digest` |
| Read back after cleanup | `apply_cleanup` returns full post-cleanup registry + tombstones |

### Tests
- M5 regression: `tests/test_checkpoint_expiry_cleanup.py` (13 cases)
- NA81 delta: `tests/test_checkpoint_expiry_cleanup_na81.py` (13 cases)

### Classification
- **DELTA_REQUIRED** — Existing code lacked `PROTECTED_CANONICAL_TYPES` and `retained_canonical_evidence`; mislabeled disposable canonical evidence could tombstone. NA81 brief explicitly requires defense-in-depth retention.
