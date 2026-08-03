# SCRUM-208 Requirements — CAS Write Guard M5

## Objective
Advance `runtime_checkpoint.cas-write-guard` from M2 to `M5_REPLAY_SAFE`. The implementation originated from `c28d0956b36f2894e369a24dfc245601bc628340` and is reconciled without history rewrite onto protected base `f9b04561437eaebd2c2711999b622029468c3551`.

## EARS requirements
1. **When** a guarded write is attempted, **the node shall** compare expected and observed revisions before mutation.
2. **If** revision, task, repository, branch, base SHA, scope, lease owner/token/expiry, or fencing evidence mismatches, **the node shall** reject without mutating newer state.
3. **When** a write is rejected, **the node shall** return latest observed state and a deterministic reconciliation route, with automatic retry disabled.
4. **When** a write succeeds, **the node shall** advance revision monotonically and emit auditable decision/effect evidence.
5. **If** the same idempotency key was already committed, **the node shall** return the committed readback without a second event or state change.

## Acceptance
- Revision match/mismatch, stale fencing, stale lease, expired lease, duplicate owner, scope/base drift, duplicate effect, crash-after-commit, restart replay, and schema validation are tested.
- Existing revision-only checkpoint callers remain compatible.
- No G4/G5/G6 authority is granted.
