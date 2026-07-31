# SCRUM-243 — lease expiry recovery M5

Adds deterministic lease-expiry recovery routing for `failure_recovery.lease-expiry-recovery`.

## Added

- Lease expiry recovery decision utility.
- JSON schema for lease-expiry recovery decisions.
- Unit tests for expiry, readback, monotonic fencing, duplicate-agent race, side-effect reconciliation, lease reacquisition, and replay equivalence.

## Boundaries

No descriptor identity, registry, deployment, release, production data/configuration, secret, credential, or migration change.
