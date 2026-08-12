# SCRUM-322 — NA81 repo_delivery.ci-failure-repair delivery evidence

Completes `SCRUM-322` (`repo_delivery.ci-failure-repair`) as VERIFIED_REUSE against the
NA81 execution brief:

- Adds `tests/test_ci_failure_repair_na81.py` pinning the current SCRUM-322 requirements:
  typed blockers for external / unknown / scope-missing (authority-lacking) failures,
  bounded-repair scope enforcement, new-head evidence invalidation, no-merge authority,
  and replay/idempotency conflict detection.
- Adds `.gwc/tasks/SCRUM-322/DELIVERY_EVIDENCE.md` requirement→code→test map on the exact
  pre-prod SHA `b3480ddffcae74ba8428dde914244fca810b5be3`.

Implementation already merged to `pre-prod`; no code delta required. Authority boundary
g2_required (G2_EXECUTION + G3_PR) — no merge/deploy/G4/G6. Parent authority
AR-SCRUM288-20260811-R4 (issue #232).
