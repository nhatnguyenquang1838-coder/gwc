# REVAMP-GWC-023 — package export node family

## Summary

Adds the seventh controlled node catalog batch for deterministic package build, export, manifest, readback, and smoke verification behavior.

## Scope

- Adds exactly nine `package_export` runtime node descriptors.
- Reuses the existing consumer package export rule, exporter, manifest schema, and smoke verifier.
- Adds schema/path safety, generated governance tree, manifest generation, hash verification, smoke verification, and failure-routing nodes.
- Adds a stdlib family validator and focused unit tests.
- Exports the family artifacts through `projects/gwc/package.yaml` without changing `package_version`.

## Guardrails

- Every node uses `canonical=delivery_evidence`.
- Every node uses `authority_boundary=g2_required`.
- Node gates are limited to `G2_EXECUTION` and `G3_PR`.
- No exporter rewrite, package publishing, or consumer repository update.
- No merge, auto-merge, deploy, release, production configuration/data, credential, secret, or migration authority.
