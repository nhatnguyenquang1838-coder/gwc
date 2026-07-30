# SCRUM-240 — stale-session-reconciliation M5 slice

- Added deterministic stale session reconciliation router.
- Added stale owner/checkpoint supersede routing.
- Added dirty working tree and pending action reconciliation routing.
- Added replay-equivalence tests.

Boundaries: no main write, merge, deploy, release, production data, secrets or migration.
