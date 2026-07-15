# Requirements Document

## Introduction

Rental Home already has repository workflow validation commands, Kiro specs, agent roles, isolated worktree rules, and a DS MCP connection. Pilot v1 needs a machine-readable validation adapter that a QA Agent can run and submit as structured evidence.

This spec extends the existing repository workflow validator. It does not change Rental Home business behavior, Supabase schema, RLS, authentication, production configuration, or production data.

## Glossary

| Term | Definition |
|---|---|
| Adapter | Rental Home command/output contract used by the Pilot QA stage |
| Workflow Validator | Existing `pnpm run workflow:validate` repository validation command |
| JSON Report | Deterministic machine-readable validation output |
| Human Report | Existing readable terminal output |
| QA Evidence | DS MCP payload that references adapter results for an exact PR head SHA |
| Runtime SSOT | DS Admin state for Pilot execution |
| Projection | Repository task state rendered from runtime evidence without overriding it |

## Requirements

### Requirement 1: Machine-Readable Validation Output

**User Story:** As a QA Agent, I want deterministic JSON validation output, so that I can submit structured evidence without parsing terminal prose.

#### Acceptance Criteria

1. WHEN the workflow validator is executed with JSON output enabled THEN it SHALL emit valid JSON to the configured output stream or file.
2. THE JSON report SHALL include schema version, repository, spec/task identifiers when available, result, checks, findings, and timestamp.
3. THE report SHALL use stable check and finding codes.
4. THE report SHALL be deterministic for the same repository state except for explicitly documented timestamps or durations.
5. Existing human-readable validation output SHALL remain available.

### Requirement 2: Exact Repository State Metadata

**User Story:** As a Reviewer, I want validation tied to a precise repository state, so that stale results cannot be reused.

#### Acceptance Criteria

1. THE adapter SHALL include current branch and full head SHA when Git metadata is available.
2. THE adapter SHALL include the expected PR head SHA when supplied by the QA task.
3. IF current head SHA differs from expected head SHA THEN the adapter SHALL fail with a stable mismatch finding.
4. THE adapter SHALL include a bounded list of changed files or a hash/reference to the reviewed diff scope.
5. THE adapter SHALL NOT expose credentials or sensitive environment values.

### Requirement 3: Pilot Runtime Projection

**User Story:** As a Tech PM, I want repository status to reflect Pilot runtime evidence without becoming a competing source of truth.

#### Acceptance Criteria

1. Pilot tasks SHALL declare `tracking_mode: ds_admin_runtime`.
2. The adapter MAY read local task/spec files to validate consistency.
3. The adapter SHALL report a mismatch when repository projection conflicts with supplied DS Admin runtime state.
4. The adapter SHALL NOT mutate DS Admin state.
5. Repository task files SHALL NOT override Pilot claim, lease, PR, CI, or QA state.

### Requirement 4: QA-Safe File Boundary

**User Story:** As a project owner, I want QA changes limited to approved test and adapter files, so that QA cannot alter application behavior to make tests pass.

#### Acceptance Criteria

1. QA task scope SHALL list exact writable files or modules.
2. QA SHALL NOT modify Rental Home production application behavior.
3. IF QA modifies files outside the approved scope THEN validation SHALL fail with a scope-violation finding.
4. QA changes MAY add or update focused adapter tests when explicitly included in the task envelope.
5. No Supabase migration, RLS, auth, package-script, CI, or deployment file SHALL be changed unless separately scoped and approved.

### Requirement 5: Pass, Failure, and Blocked Results

**User Story:** As an operator, I want consistent result semantics, so that State Engine transitions are deterministic.

#### Acceptance Criteria

1. The adapter result SHALL be one of `passed`, `failed`, or `blocked`.
2. A validation failure caused by repository behavior SHALL return `failed`.
3. Missing required context, wrong head SHA, unsafe environment, or unavailable prerequisite SHALL return `blocked`.
4. Process exit codes SHALL be documented and stable.
5. Findings SHALL include severity, code, summary, and path/line when available.

### Requirement 6: Compatibility

**User Story:** As a maintainer, I want the adapter to reuse existing workflow validation, so that Pilot v1 does not create duplicate governance logic.

#### Acceptance Criteria

1. The implementation SHALL reuse `scripts/workflow/validate-repo-state.mjs` and existing workflow libraries where practical.
2. The implementation SHALL NOT create a second independent repository state validator.
3. Existing `pnpm run workflow:validate` behavior SHALL remain compatible.
4. New tests SHALL cover pass, fail, blocked, head mismatch, scope mismatch, and malformed runtime input.
5. `pnpm run typecheck`, focused tests, `pnpm run workflow:validate`, and `pnpm run build` SHALL pass before Draft PR delivery.

### Requirement 7: Security and Data Boundaries

**User Story:** As a security owner, I want the Pilot adapter isolated from production data and secrets, so that workflow testing cannot affect tenants.

#### Acceptance Criteria

1. The adapter SHALL operate on repository and supplied task metadata only.
2. The adapter SHALL NOT read or write production Supabase data.
3. The adapter SHALL NOT require service-role credentials.
4. The adapter SHALL redact token-like values from captured command output.
5. Deployment, production configuration, migration, and production-data operations SHALL remain separately gated.
