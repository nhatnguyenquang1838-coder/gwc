# SCRUM-214 — CI Evidence Capture M5 Requirements

## Objective
Implement `validation_quality.ci-evidence-capture` as a deterministic, exact-head, replay-safe G3 evidence node used by the active SCRUM-256 Client-runtime vertical slice.

## Functional requirements
1. Bind input/output to task ID, repository, branch, base SHA, exact head SHA, scope hash, graph revision, provider observation and evidence digest.
2. Reuse `tools/node_architect/ci_run_capture.py` for provider payload classification and canonical digests.
3. Reuse `tools/node_architect/checkpoint_store.py` to persist before waiting, bounded polling or external-observation continuation.
4. Emit only the closed reason codes `CI_SUCCESS`, `CI_FAILURE`, `CI_CANCELLED`, `CI_PENDING`, `CI_UNAVAILABLE_AT_CHECK`, `CI_TIMEOUT`, `STALE_HEAD`, and `CI_SHA_MISMATCH`.
5. Absence, empty PR-filtered results, unknown provider state, timeout or SHA mismatch must never become PASS.
6. Mark evidence stale when the requested exact head changes.
7. Reconcile timeout/unknown state through readback; never blindly redispatch.
8. Identical input/evidence replay must return the same digest without duplicate evidence or checkpoint effects.
9. Integrate the handler into the existing SCRUM-259 Client adapter without implementing SCRUM-215 or SCRUM-219.
10. Preserve zero G4/G5/G6 authority.

## Acceptance
- Focused terminal, pending, unavailable, timeout, drift, duplicate, crash and replay tests pass.
- Client-runtime integration consumes the new handler and fails closed on invalid evidence.
- Exact final PR-head CI and independent G3 review are required before task acceptance.
