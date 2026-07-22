# REVAMP-GWC-022 — sync projection node family

## Summary

Adds the sixth controlled node catalog batch for audit-only synchronization and projection behavior.

## Scope

- Adds exactly nine `sync_projection` runtime node descriptors.
- Models DS Admin, Task Center, and external audit projections without making them canonical.
- Adds source-authority, drift, readback reconciliation, failure routing, evidence linking, and privacy-boundary nodes.
- Adds a stdlib family validator and focused unit tests.
- Exports the family artifacts through `projects/gwc/package.yaml` without changing `package_version`.

## Guardrails

- Every node uses `canonical=audit_projection`.
- Every node uses `authority_boundary=g2_required`.
- Node gates are limited to `G2_EXECUTION` and `G3_PR`.
- No DS Admin, Task Center, connector, runtime engine, scheduler, or worker implementation.
- No merge, auto-merge, deploy, release, production configuration/data, credential, secret, or migration authority.
