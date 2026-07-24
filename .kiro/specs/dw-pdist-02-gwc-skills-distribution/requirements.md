# Requirements Document

## Introduction

DW-PDIST-02 adds a governed, skills-only GWC provider package for DW Power Distribution v1. The package must be installable without cloning the GWC development repository, must preserve GWC authority boundaries, and must not contain task evidence, generated plans, dashboards, secrets, caches, or populated runtime data.

## Glossary

- **GWC Provider Package**: The curated archive built from `distribution/power-package.yaml`.
- **Shared Foundation**: DW-SuperApps Power Distribution v1 at commit `4e552ea3d915a4790814b08b3155c66e3c5736a1`.
- **Staging Tree**: The single validated directory used to generate both release ZIP and `power-dist` output.
- **Runtime Root**: Consumer-owned `.gwc`, created empty during installation.
- **Authority Boundary**: GWC gate rules that prevent installation or packaging from granting repository, PR, merge, deploy, release, credential, or production authority.

## Requirements

### Requirement 1: Curated Dependency Closure

**User Story:** As a GWC consumer, I want the G0/G1 skills and their verified internal dependencies packaged together, so that the skills work without the provider development repository.

#### Acceptance Criteria

1. WHEN the recipe is validated THEN the system SHALL declare `skills/gwc-g0/SKILL.md` and `skills/gwc-g1/SKILL.md` as package entrypoints.
2. WHEN the package is built THEN the system SHALL include the schemas, templates, generators, validators, offline skill library, project instructions, agent instructions, and core contracts required by those entrypoints.
3. WHEN a declared entrypoint or required dependency is absent THEN validation SHALL fail before publication.

### Requirement 2: Skills-Only Boundary

**User Story:** As a GWC maintainer, I want an explicit allowlist and fail-closed exclusions, so that operational evidence and unrelated application assets cannot enter the package.

#### Acceptance Criteria

1. WHEN the package is built THEN the system SHALL NOT include `.gwc/**`, `.ua/**`, `.task-me/**`, generated tasks or plans, dashboards, frontends, tests, releases, caches, logs, or secret-bearing files.
2. WHEN a provider-defined forbidden path or content pattern is detected THEN the builder SHALL fail.
3. WHEN package includes are reviewed THEN they SHALL use explicit files or narrow directories rather than a repository-wide wildcard.

### Requirement 3: Neutral Consumer Configuration

**User Story:** As a consumer application owner, I want host-neutral GWC defaults and a schema, so that runtime configuration can be reviewed before use.

#### Acceptance Criteria

1. WHEN the default configuration is parsed THEN it SHALL identify `gwc`, `.gwc`, the GWC project profile, Jira MCP task tracking, and connector preference without credentials or environment-specific paths.
2. WHEN configuration is validated THEN additional undeclared fields SHALL be rejected.
3. WHEN the package is installed THEN configuration SHALL NOT create tasks, gates, approvals, branches, PRs, or external writes.

### Requirement 4: Deterministic Shared Publishing

**User Story:** As a release operator, I want GWC publishing to reuse the shared DW foundation, so that ZIP and `power-dist` outputs have identical validated content semantics.

#### Acceptance Criteria

1. WHEN the workflow runs THEN it SHALL call the reusable DW workflow by immutable commit `4e552ea3d915a4790814b08b3155c66e3c5736a1`.
2. WHEN a package version is built THEN release ZIP and `power-dist` SHALL derive from one staging tree.
3. WHEN this task is validated THEN release and distribution-branch publication inputs SHALL remain disabled unless separately authorized.

### Requirement 5: Consumer-Owned Runtime Data

**User Story:** As a consumer, I want installation to preserve runtime ownership, so that installing GWC does not fabricate governance state.

#### Acceptance Criteria

1. WHEN installed into a clean consumer THEN the runtime SHALL create an empty `.gwc` root.
2. WHEN installation completes THEN `.gwc` SHALL contain no task, gate, decision, approval, envelope, or evidence record.
3. WHEN GWC is uninstalled normally THEN consumer runtime data SHALL remain preserved.

### Requirement 6: Governed Validation and Delivery

**User Story:** As a governance owner, I want exact-scope validation and audit evidence, so that the provider change does not weaken GWC controls.

#### Acceptance Criteria

1. WHEN implementation is complete THEN G0/G1/G2 artifacts SHALL validate against the protected base.
2. WHEN provider tests run THEN they SHALL verify dependency references, exclusions, schema validity, workflow pinning, and runtime ownership.
3. WHEN the branch is pushed THEN no PR, merge, release, `power-dist` publication, deployment, credential operation, or production operation SHALL have occurred.
