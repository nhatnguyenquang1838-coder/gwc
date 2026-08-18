# SCRUM-361 — failure_recovery.timeout-recovery NA81-F8 maturity delta

## Type

```text
feature
```

## Summary

Promotes `failure_recovery.timeout-recovery` to cover the full NA81-F8 brief
(Jira SCRUM-361 / GitHub #296). The prior implementation (historical SCRUM-238)
handled `UNKNOWN`, `COMMITTED`, `FAILED`, and `ZERO_EFFECT` states but left a
genuine gap: a **real pending** effect and an interruption were not distinguished
from the ambiguous `UNKNOWN` case and fell through to the generic unsupported
branch. This delta implements the two missing, explicitly required recovery
states and keeps the decision fully deterministic and replay-safe.

- Added `effect_status == "PENDING"` -> `RECONCILE` / `PENDING_EFFECT_RECONCILE`:
  a real in-flight effect that has not been read back must be reconciled before
  any retry so duplicate effects are impossible.
- Added `effect_status == "INTERRUPTED"` -> `RECONCILE` / `INTERRUPTED_UNKNOWN_EFFECT`:
  the operation was interrupted before its result was observed, so the external
  effect is unknown and must be reconciled before retry (family invariant
  `UNKNOWN_EFFECT => READBACK_OR_RECONCILE_BEFORE_RETRY`).
- Both new states preserve `blind_redispatch_allowed = False` and
  `checkpoint_required = True`; the unsupported-status fail-closed branch is
  retained for any future unknown value.
- Enriched the `timeout-recovery` node descriptor description to reflect the
  timeout / pending / interruption / unavailable-evidence / terminal-failure
  distinction required by the brief.

## Guardrails

```text
TIMEOUT_DISTINCT_FROM_UNAVAILABLE_EVIDENCE_AND_TERMINAL_FAILURE.
UNKNOWN_OR_PENDING_OR_INTERRUPTED_EFFECT => READBACK_OR_RECONCILE_BEFORE_RETRY.
RECOVERY_NEVER_BLIND_REDISPATCHES_OR_DUPLICATES_AN_EXTERNAL_EFFECT.
RECOVERY_MUST_NOT_EXPAND_SCOPE_OR_AUTHORITY.
```

## Tests

Added `tests/test_timeout_recovery_na81.py` covering every brief scenario:
zero effect, unknown effect, real pending, unavailable readback, retryable vs
exhausted retry, interruption, not-timed-out wait, committed/human, failed
terminal, replay equivalence ignoring observation time, no-duplicate-effect on
replay, distinct-effect non-equivalence, and deterministic decision digest.
