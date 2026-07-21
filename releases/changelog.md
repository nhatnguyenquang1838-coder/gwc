# Changelog

## 2026-07-21 — REVAMP-GWC-006 consumer package export

### Added

- Consumer package export rule for generated `.governance/` package boundaries.
- Package export manifest schema and deterministic `tools/export_project_package.py` exporter.
- GWC package entries for REVAMP node-architect rules, schemas, tools, and exporter distribution.

### Changed

- `projects/gwc/package.yaml` keeps `package_version: "1.16.0"` for compatibility with the existing runtime-bootstrap package assertion.
- Package notes now record REVAMP-GWC-006 as a package-entry/export rollout without presenting it as a second `Package version 1.16.0` release line.

### Hygiene

- PR #58 metadata was corrected so the body no longer claims a package-version bump to `1.17.0`.
- Release notes now document the consumer export scope that was intentionally skipped during PR #58 because the connector had no safe append primitive in that execution turn.

### Safety

- This change grants no protected-branch write outside G2, merge, deploy, release, production configuration, credential, migration, or production-data authority.

## 2026-07-21 — G0/G1 runtime bootstrap and lifecycle scope

### Added

- Runtime bootstrap evidence in G01 runtime input for selected agent runtime, execution mode, runtime profile source, connector priority, selected connector, fallback evidence, and required behavior contracts.
- G0 and G1 preflight runtime context so agents must bind G0/G1 evidence to the current runtime profile and execution mode.
- G1 intake delivery lifecycle coverage for guarded branch creation, scoped writes, validation, push, Draft PR creation/update, CI monitoring or repair, independent G3 review, and Draft-to-Ready-for-review metadata completion after G3 `PASS`.
- Profile resolver and validator flags to select exactly one active runtime profile for the current agent and fail closed when execution mode compatibility is missing.

### Changed

- GWC package version `1.16.0` distributes the runtime bootstrap evidence, lifecycle scope fields, resolver selection behavior, template updates, and regression tests.
- The G0/G1 operational runbook now requires selected runtime profile resolution and connector-role evidence before G2 handoff.

### Safety

- Ready-for-review remains G3 metadata completion only after exact-head G3 `PASS`; it grants no merge authority.
- This change grants no protected-branch write outside G2, merge, deploy, release, production configuration, credential, migration, or production-data authority.

## 2026-07-21 — Multi-profile resolver and gate response traceability

### Added

- Typed profile set composition for gate policy, agent runtime, environment, and risk profiles.
- Standard GWC profile set with ChatGPT and DWC runtime profiles, repository-governance environment, and default risk classification.
- Deterministic fail-closed profile resolver and validator with safe-path, type, ID, active-state, duplicate, and schema checks.
- Mandatory gate response trace schema, template, and validator for `Skills called`, `Started at UTC`, and `Ended at UTC`.
- Kiro requirements, design, implementation plan, and focused regression tests.

### Changed

- GWC package version `1.15.0` distributes the profile assets, schemas, response template, resolver, and validators.

### Compatibility

- `projects/gwc/project-profile.yaml` remains the active repository identity; profile sets extend rather than replace the existing mechanism.
- Resolver output is deterministic and no new runtime dependency is introduced.

### Safety

- The standard gate profile preserves G2 exact approval, G3 Draft PR and exact-head evidence, Ready-for-review metadata completion after G3 `PASS`, and separate G4 merge authority.
- This change grants no protected-branch write, merge, deploy, release, production configuration, credential, migration, or production-data authority.

## 2026-07-20 — DWC ready-for-review capability contract

### Added

- DWC capability declaration for `github_mark_pr_ready_for_review` as G3 metadata completion after exact-head G3 `PASS`.
- Approval envelope action enum entry for `mark_pr_ready_for_review` so G3/G4 preparation can represent the metadata transition explicitly.
- Regression tests for the capability guard, instruction contract, no-merge boundary, and schema action entry.

### Changed

- GWC package version `1.14.1` records the ready-for-review connector contract while keeping G4 merge authority separate.

### Safety

- The ready-for-review action grants no merge, auto-merge, deploy, release, production configuration, credential, migration, production-data, force-push, branch-deletion, or PR-base-change authority.
- If the connector tool is unavailable, DWC must report a ready-for-review blocker and wait for manual UI promotion before G4.

## 2026-07-20 — Canonical Kiro spec-driven delivery and ChatGPT task parity

### Added

- Canonical `core/KIRO_SPEC_DRIVEN_DELIVERY_RULE_v1.0.md` for reusable requirements, design, and implementation-task planning under `.kiro/specs/<SPEC-ID>/`.
- Explicit ChatGPT/local-agent runtime parity: one AgentOps/DS Admin task, legal transitions through `agent_running`, and task-scoped `.gwc/tasks/<task-id>/g0`, `g1`, and `g2` evidence before G2.
- Canonical rule registration and distribution through the `gwc`, `ds-mcp`, and `rental-home` packages.

### Changed

- GWC package version `1.14.0`, DS MCP package version `1.2.0`, and Rental Home package version `1.1.0` include the canonical rule.
- Rental Home spec guidance is now an additive adapter that retains project naming, Mermaid dependency graphs, `src/app/dependencies.ts`, Supabase access, RLS/schema, and validation constraints without duplicating the shared template.
- ChatGPT and project-consumer instructions now require the existing `.gwc/tasks/<task-id>` mechanism instead of a parallel or conversation-only task artifact format.

### Compatibility

- Existing specs are not moved or rewritten automatically.
- Project-local rules may add stricter naming, architecture, security, data, and validation constraints but may not weaken canonical GWC gates.

### Safety

- Kiro specs, task creation, `agent_running`, and valid `.gwc` artifacts are traceability only.
- This change grants no protected-branch write, merge, auto-merge, deployment, release, production configuration, credential, migration, or production-data authority.

## 2026-07-19 — DW1 connector structured trace contract

### Added

- Additive connector trace contract defining deterministic failure-stage attribution across platform runtime, connector transport, connector validation/policy, and GitHub API boundaries.
- JSON Schema for trace IDs, operation names, stage values, upstream-attempt evidence, provider request IDs, HTTP status, and normalized retry metadata.
- Contract tests for successful GitHub calls, connector-policy rejection, required error envelopes, and non-speculative safety-layer attribution.

### Changed

- DWC instructions now require structured trace evidence before naming the blocking layer.
- DWC capabilities declare structured connector tracing as `contract_defined_runtime_bootstrap_gap`.

### Limitations

- The DW1 backend source is not present in this repository. Runtime instrumentation and deployment must occur in the connector implementation repository before these fields can be treated as live runtime evidence.

### Safety

- This additive contract grants no merge, deployment, release, production configuration, credential, secret, migration, or production-data authority.

## 2026-07-19 — G0/G1 Context7-first offline skill fallback

### Added

- Deterministic offline skill library for G0 and G1 under `libs/g0-g1-skill-library/`.
- Context7-first skill resolution for G0 (`skills/gwc-g0/SKILL.md`) and G1 (`skills/gwc-g1/SKILL.md`) with bundle-atomic fallback policy.
- Pinned offline manifest, SHA-256 verification, provenance notice, and G0/G1-compatible normalized skill cards:
  - `g0-context-loading`
  - `g1-intake-options-preflight`
  - `g1-decision-record`
  - `g0-g1-approval-envelope`
- Contract tests for Context7-first ordering, bundle-atomic fallback, offline file hashes, required skill composition, and exact evidence boundaries.
- GWC project package entries distributing the new G0/G1 skill library.
