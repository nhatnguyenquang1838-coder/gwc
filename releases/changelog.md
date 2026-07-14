
# Changelog

## 2026-07-14

### Added

- Agent-readable GWC G0 skill wrapper for project activation, repository and
  protected-base verification, policy/source resolution, connector and task
  context checks, freshness handling, and a bounded handoff into G1.
- Agent-readable GWC G1 skill wrapper for intake, existing-mechanism inspection,
  brainstorming, preflight, explicit decision preparation, and G2 handoff
  preparation after G0 is ready.
- GWC project package version `1.4.0` distributes both skills as governed source
  instruction artifacts.

### Changed

- G1 now consumes a verified G0 handoff instead of owning a duplicate context
  reconstruction step.
- G1 skill expanded to version `0.3.0` with phase boundaries, artifact contract
  summaries, intake matrix, option selection rules, preflight outcomes, decision
  status rules, G2 handoff shape, and completion markers.
- G1 now requires run identity metadata for each session: `run_id`,
  `workspace_mode`, `workspace_root`, repository artifact write state,
  conflict policy, and verification mode.
- G1 chat-only mode is explicitly conversation-local and must not write
  `.gwc/g1/...`; concurrent artifact runs must use isolated workspaces or fail
  closed on unknown workspace ownership.
- The skills document that task and risk facts are runtime/preflight inputs but
  are not fields in the canonical G0 context snapshot schema version `1.0`.

### Safety

- The G0 and G1 skills are instruction-only and do not add validators,
  executable tools, repository write authority, merge authority, deployment
  authority, production configuration, credentials, or production-data access.
- Anthropic and Superpowers skill patterns are used as reference material only;
  they cannot override GWC protected-base governance.

## 2026-07-13

### Added

- Versioned G01 decision input schema and deterministic options/decision capture
  tool with explicit-choice enforcement, scope hashing, and full workspace validation.
- Decision capture fixture and six focused tests covering PASS, blocked,
  non-explicit, rejected, duplicate-option, and CLI end-to-end behavior.
- Versioned G01 runtime input schema and deterministic generator for G0 context,
  G1 intake, and G1 preflight artifacts.
- Fail-closed runtime checks for repository identity, required sources, DS Admin
  task claim, intake completeness, and R2/R3 human direction.
- Runtime fixture, five focused unit tests, package assets, and usage documentation.
- Versioned G0 context and G1 intake, preflight, options, and decision schemas.
- Deterministic fail-closed G0/G1 validator, reusable YAML templates, fixtures,
  unit tests, and lifecycle documentation.
- Base drift evaluation policy, schema, evaluator, tests, and documentation for
  evaluating protected-base SHA changes after approval.

### Changed

- GWC project package version `1.3.0` includes G0/G1 lifecycle documentation,
  runtime and decision input schemas, generators, and reusable templates.
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
