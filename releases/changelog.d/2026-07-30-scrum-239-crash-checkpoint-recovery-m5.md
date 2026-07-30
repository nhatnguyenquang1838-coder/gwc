# SCRUM-239 — crash-checkpoint-recovery M5 slice

- Added deterministic crash checkpoint recovery decision router.
- Added canonical checkpoint and pending-action readback routing.
- Added no-duplicate-effect handling for unknown or committed post-crash effects.
- Added schema and replay-equivalence tests for crash resume.
- Bound implementation to `failure_recovery.crash-checkpoint-recovery`.

Boundaries: no main write, merge, deploy, release, production data, secrets or migration.
