# SCRUM-198 — ci-run-capture M5 slice

- Added exact-head CI observation normalization.
- Added fail-closed handling for absent provider data and SHA mismatch.
- Added pending-CI checkpoint requirement.
- Added CI observation schema and replay-equivalence tests.

Boundaries: no main write, merge, deploy, release, production data, secrets or migration.
