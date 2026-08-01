# SCRUM-214 — CI Evidence Capture M5 Design

## Reuse-first design

`Client runtime evidence payload`
→ `validation_quality.ci-evidence-capture`
→ `ci_run_capture.classify_provider_payload / capture_ci_observation`
→ terminal decision **or** checkpoint-before-wait
→ immutable evidence digest

## New utility
`tools/node_architect/ci_evidence_capture.py` is a pure orchestration/decision adapter. It does not call GitHub directly. The caller supplies provider readback and the utility normalizes, binds and classifies it.

## State model
- Terminal success → `PASS / CI_SUCCESS`.
- Terminal failure → `BLOCKED / CI_FAILURE`.
- Cancelled → `BLOCKED / CI_CANCELLED`.
- Pending → `WAIT / CI_PENDING`, persist checkpoint first.
- Provider unavailable or empty authoritative readback → `WAIT / CI_UNAVAILABLE_AT_CHECK`, persist checkpoint first.
- Timeout → `WAIT / CI_TIMEOUT`, persist checkpoint and require readback reconciliation.
- Head drift → `BLOCKED / STALE_HEAD`.
- Candidate SHA mismatch → `BLOCKED / CI_SHA_MISMATCH`.

## Replay
Canonical evidence excludes observation time from the stable replay key. A matching prior result returns the same result/digest and does not append another checkpoint/event. A conflicting prior result for the same idempotency key fails closed.

## Integration boundary
Update only the existing `client_runtime.py` handler for SCRUM-214. Downstream quality and G3 handlers remain fail-closed placeholders for SCRUM-215 and SCRUM-219.

## Rollback
Revert the utility, schema, tests and Client handler binding. Existing `ci_run_capture.py` and `checkpoint_store.py` remain unchanged compatibility surfaces.
