# SCRUM-206 — runtime_checkpoint.lease-acquisition (MAT-F4-N05)

```text
Task: SCRUM-206
Node: runtime_checkpoint.lease-acquisition
Family: runtime_checkpoint
Maturity: M2 -> M5_REPLAY_SAFE
Authority boundary: G2_EXECUTION
```

## Added

- Added `tools/node_architect/lease_acquisition.py`: a deterministic, replay-safe
  lease-acquisition decision utility.
  - `decide_lease_acquisition(...)` evaluates competing-lease evidence and
    returns a monotonic `fencing_token` when acquisition is allowed.
  - Fail-closed binding: rejects acquisition when task/repository/scope/gate
    identity is missing or ambiguous.
  - Outcomes: `ACQUIRED`, `FENCE_STALE_WORKER`, `FENCE_DUPLICATE_AGENT`,
    `RECONCILE`, `REACQUIRE_REQUIRED`, `SCOPE_MISMATCH`.
  - `is_replay_equivalent(...)` provides replay-read compatibility ignoring
    `observed_at`.
- Added `schemas/lease-acquisition-decision.schema.json` for decision validation.
- Added `tests/test_lease_acquisition.py` covering competing-agent acquisition,
  stale owner, expired lease, scope mismatch, crash-before-persist purity,
  fencing monotonicity, and replay equivalence.
- Added the G0/G1/G2 task-scoped gate artifacts under `.gwc/tasks/SCRUM-206/`.

## Guardrails

```text
No merge authority.
No deploy/release.
No production data/config.
No runtime engine / scheduler / worker implementation.
No scope expansion beyond the approved node.
Lease persistence remains the caller's responsibility via checkpoint_store.py.
```
