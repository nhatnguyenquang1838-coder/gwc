# SCRUM-333 runtime_checkpoint.checkpoint-expiry-cleanup NA81 canonical-evidence retention delta

- Added `PROTECTED_CANONICAL_TYPES` frozenset covering approval, CI, PR, merge,
  and G0-G6 evidence.
- Updated `classify_entry` to return `RETAIN_CANONICAL` for protected canonical
  artifact types before any retention-class or expiry check — defense-in-depth
  against mislabeled disposable corruption.
- `apply_cleanup` now emits `retained_canonical_evidence` list in the result.
- Added focused NA81 tests `tests/test_checkpoint_expiry_cleanup_na81.py`
  (13 cases): approval/CI/PR/merge/G0-G6 retention, ambiguous fail-closed,
  concurrent resume race, idempotent rerun, destructive-negative.
