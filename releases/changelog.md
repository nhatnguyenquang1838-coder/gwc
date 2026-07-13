
# Changelog

## 2026-07-13

### Added

- Versioned G0 context and G1 intake, preflight, options, and decision schemas.
- Deterministic fail-closed G0/G1 validator, reusable YAML templates, fixtures,
  unit tests, and lifecycle documentation.
- Base drift evaluation policy, schema, evaluator, tests, and documentation for
  evaluating protected-base SHA changes after approval.

### Changed

- GWC project package version `1.1.0` includes G0/G1 lifecycle documentation.
- GWC project package includes the base drift policy as a governed source
  instruction artifact.
- Repository CI runs governance unit tests in addition to instruction validation.

## 2026-07-13

### Changed

- DWC generated artifact refreshes may auto-wrap bounded guarded-branch
  integrity updates in an internal approval envelope when the generator is
  verified and validation passes.
- DWC keeps `G4` merge as a separate human approval boundary.

### Added

- Active `gwc` self-governance project profile and package.
- DWC repository operation contract and machine-readable capabilities.
- DS Admin traceability for GWC modifying tasks.

### Changed

- DWC read-only inspection is automatic for the verified GWC repository.
- DWC may perform bounded non-risk writes on a dedicated branch and deliver a
  Draft PR without repeated per-operation approval prompts.
- DWC repository writes are task-bounded instead of restricted to a fixed file
  allowlist.

### Safety

- Explicit human direction remains required for financial, architecture,
  security-boundary, production configuration, credential, production-data,
  destructive, irreversible, and broad-blast-radius changes.
- Direct protected-branch pushes, merge, deployment, production operations,
  force-push, branch deletion, and shared-history rewrite remain prohibited or
  separately gated.

## 2026-07-12

### Added

- Initial `instruction-governance` control-plane repository.
- Canonical Coding Project Governance v1.0.
- E2E Draft PR delivery rule.
- Local Agent Rule.
- Copyable User Command Format Rule.
- DS MCP, Rental Home, and PM Skills project packages.
- Mandatory DS Admin task claim rule for DS MCP.
- InstructionOps Agent contract and capabilities.
- Coding-agent bootstrap.
- JSON schemas for instructions, packages, rollouts, and approval envelopes.
- Validation, package build, diff, and rollout verification tools.
- GitHub Actions validation, package build, and manual release workflows.

### Safety

- Rental Home writes are disabled pending repository verification.
- PM Skills writes are disabled pending canonical repository assignment.
- No deployment, production configuration, credential, migration, or
  production-data authority is included.
