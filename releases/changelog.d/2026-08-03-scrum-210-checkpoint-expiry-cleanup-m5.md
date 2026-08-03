# SCRUM-210 — runtime_checkpoint.checkpoint-expiry-cleanup (MAT-F4-N09)

```text
Task: SCRUM-210
Node: runtime_checkpoint.checkpoint-expiry-cleanup
Family: runtime_checkpoint
Maturity: M1 -> M5_REPLAY_SAFE
Authority boundary: G2_EXECUTION
```

## Added

- Added `tools/node_architect/checkpoint_expiry_cleanup.py`: a deterministic,
  replay-safe expiry-cleanup node implementation (MAT-F4-N09, M5_REPLAY_SAFE).
  - `classify_entry(...)` maps each registry entry to one of
    `RETAIN_GOVERNANCE`, `RETAIN_AUDIT`, `RETAIN_APPEND_ONLY`,
    `RETAIN_ACTIVE_RESUME`, `TOMBSTONE_EXPIRED`, or `RETAIN_VALID`.
  - EARS #1: cleanup identifies only expired disposable checkpoint hints and
    interrupt frames.
  - EARS #2: governance, audit, and append-only runtime evidence are retained
    verbatim (never tombstoned or deleted).
  - EARS #3: a still-valid active resume path wins over cleanup — if the
    resume token is unexpired, its entry is retained even when its hint would
    otherwise be expired.
  - EARS #4: removal emits an auditable `TOMBSTONE` marker with a reason and a
    tombstone digest; `apply_cleanup(...)` returns an immutable result with a
    replay `cleanup_digest`.
  - `is_replay_equivalent(...)` proves cleanup is idempotent across re-runs:
    the same registry + policy yield the same tombstone outcome regardless of
    per-run `cleanup_id`.
- Added `tests/test_checkpoint_expiry_cleanup.py` (13 tests) covering expired
  hint/interruption-frame cleanup, active-token preservation, governance/audit/
  append-only retention, audit tombstone, the concurrent-resume race, replay
  equivalence, and idempotency on already-tombstoned entries.
- Added the G0/G1/G2 task-scoped gate artifacts under `.gwc/tasks/SCRUM-210/`.

## Validation

- `PYTHONPATH=. python tools/node_architect/validate_node_catalog_runtime_checkpoint.py`
  -> PASS (9 nodes intact; no node file added).
- `PYTHONPATH=. python tests/test_checkpoint_expiry_cleanup.py` -> 13 passed.
- Full suite `python -m unittest discover -s tests -p "test_*.py"` -> 860 passed.

## Guardrails

```text
No merge authority.
No deploy/release.
No production data/config.
No runtime engine / scheduler / worker implementation.
No scope expansion beyond the approved node.
```
