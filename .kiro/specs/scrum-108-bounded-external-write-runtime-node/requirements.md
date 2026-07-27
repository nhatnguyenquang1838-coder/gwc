# SCRUM-108 Requirements — bounded external-write runtime node

## Objective
Implement a bounded external-write runtime helper/classifier for GWC that models one external mutation intent, requires persisted intent before dispatch, binds idempotency and exact scope, requires live readback, reconciles ambiguous timeout outcomes, and prevents duplicate side effects.

## Acceptance Criteria
- AC-1: A persisted intent with task id, scope hash, idempotency key, checkpoint revision, and lease/fencing token is required before mutation dispatch.
- AC-2: Scope mismatch, stale checkpoint, stale lease, or missing idempotency key forbids dispatch.
- AC-3: Timeout before effect is retryable only after readback confirms zero matching effects.
- AC-4: Timeout after effect is PASS_RECONCILED only when readback confirms exactly one matching effect for the same idempotency key and scope.
- AC-5: Ambiguous post-state forbids repeat dispatch and requires human takeover evidence.
- AC-6: Tests cover duplicate-worker, stale checkpoint, timeout-before-effect, timeout-after-effect, ambiguous readback, and human takeover packet cases.
