# SCRUM-238 — timeout-recovery M5 slice

- Added deterministic timeout recovery decision router.
- Added no-blind-redispatch handling for unknown external effects.
- Added readback-not-verified reconciliation routing.
- Added bounded retry and checkpoint-required classification.
- Added schema and replay-equivalence tests.

Boundaries: no main write, merge, deploy, release, production data, secrets or migration.
