# Requirements Document

## Introduction

SCRUM-89 strengthens the GWC G0/G1 → G2 handoff so implementation-capable work cannot reach source mutation without one validated, durable implementation plan. The workflow must reuse a current Kiro spec when possible, call Task Me when planning complexity warrants it and the capability is available, or generate a standard Kiro spec as the controlled fallback.

## Glossary

- **Canonical task UID:** Stable work identity shared across Jira, GWC artifacts, Kiro specs, branches, PRs, and audit evidence.
- **Implementation plan:** A validated requirements/design/tasks package bound to one repository and protected-base revision.
- **Task Me:** Planning capability used for codebase analysis, impact analysis, dependency ordering, complexity and test guidance.
- **Kiro Spec:** Project-local spec folder containing `requirements.md`, `design.md`, and `tasks.md`.
- **Plan handoff:** Durable plan reference copied from G1 evidence into the G2 authorization and execution evidence.
- **Material drift:** Change to task UID, repository, protected-base SHA, scope, architecture, security/data impact, or required files that invalidates the plan.

## Requirements

### Requirement 1: Deterministic plan applicability

**User Story:** As a GWC operator, I want G0/G1 to classify whether an implementation plan is required, so that trivial administrative work is not over-processed and implementation work is never under-planned.

#### Acceptance Criteria

1. WHEN G0/G1 evaluates a task THEN the system SHALL record `required` or `not_applicable` with an explicit reason.
2. WHEN work changes behavior, interfaces, schemas, workflow, architecture, migration logic, or multiple implementation files THEN the system SHALL classify the plan as required.
3. WHEN work is purely read-only, communication-only, projection-only, approval recording, status inspection, or a clearly trivial bounded edit THEN the system MAY classify the plan as not applicable.
4. WHEN applicability evidence is missing THEN G1 SHALL NOT PASS.

### Requirement 2: Existing-plan discovery and reuse

**User Story:** As a maintainer, I want G0/G1 to reuse a valid existing plan, so that duplicate or conflicting specifications are not created.

#### Acceptance Criteria

1. WHEN a plan is required THEN the system SHALL search `.kiro/specs/**` and any project-approved canonical plan location.
2. WHEN exactly one current matching plan exists THEN the system SHALL verify task UID, repository, protected-base SHA, scope, requirements, design, task ordering and codebase relevance before reuse.
3. WHEN multiple candidate plans conflict THEN G1 SHALL stop with a plan conflict rather than selecting one silently.
4. WHEN an existing plan is stale or incomplete THEN the system SHALL refresh it through Task Me or Kiro fallback before G1 PASS.

### Requirement 3: Task Me routing with Kiro fallback

**User Story:** As a delivery lead, I want Task Me called for complex planning when available, with a deterministic Kiro fallback, so that planning cannot fail merely because one capability is unavailable.

#### Acceptance Criteria

1. WHEN impact analysis, complexity estimation, dependency DAG, file/symbol targeting, test design or multi-step implementation guidance materially improves safety THEN Task Me SHALL be marked applicable.
2. WHEN Task Me is applicable and available THEN G0/G1 SHALL invoke it and retain durable output evidence.
3. WHEN Task Me is unavailable or unsupported THEN G0/G1 SHALL generate or refine a Kiro Spec under `.kiro/specs/<SPEC-ID-kebab-case>/` and record the fallback reason.
4. WHEN no legal planning route exists THEN G1 SHALL NOT PASS.

### Requirement 4: Structured G1 implementation-plan evidence

**User Story:** As a G2 executor, I want a complete plan reference in the G1 artifact, so that I can prove what plan governs implementation.

#### Acceptance Criteria

1. WHEN a plan is required THEN the accepted G1 artifact SHALL record applicability, reason, source, task UID, repository, protected-base SHA, plan root, requirements/design/tasks paths, plan revision, validation status/evidence, generator and UTC generation time.
2. WHEN any required plan field is missing, stale, mismatched or unvalidated THEN G1 SHALL NOT PASS.
3. WHEN a plan is not applicable THEN G1 SHALL record the reason and SHALL NOT fabricate plan paths.
4. WHEN G1 artifacts are generated THEN all plan references SHALL use durable repository paths or approved immutable artifact URLs.

### Requirement 5: G2 read-before-write enforcement

**User Story:** As a governance owner, I want G2 to read and validate the exact plan before changing source, so that implementation cannot diverge from approved intent.

#### Acceptance Criteria

1. BEFORE any G2 repository mutation, the executor SHALL read all referenced plan documents or the approved equivalent package.
2. BEFORE any G2 repository mutation, the executor SHALL verify task UID, repository, protected-base SHA, plan revision, scope and authorized file/action boundaries.
3. WHEN material drift is detected THEN G2 SHALL stop and return to G1.
4. WHEN plan evidence is absent or unreadable THEN G2 SHALL deny the write action.
5. WHEN G2 proceeds THEN its envelope, G3 delivery record and PR body SHALL preserve the same plan reference and canonical task UID.

### Requirement 6: Validation, compatibility and traceability

**User Story:** As a GWC maintainer, I want schema, runtime and regression coverage for the plan handoff, so that existing valid artifacts remain compatible while new work is enforced.

#### Acceptance Criteria

1. WHEN legacy G1 artifacts predate the extension THEN validators SHALL preserve explicitly supported compatibility and SHALL prevent partial new-format enforcement.
2. WHEN new artifacts use the implementation-plan extension THEN schemas and validators SHALL enforce the complete field set.
3. Tests SHALL cover existing-plan reuse, Task Me generation, Kiro fallback, not-applicable classification, missing plan, invalid plan, stale revision, base drift and G2 read enforcement.
4. Package exports and documentation SHALL include every new or changed reusable governance artifact.
5. No change SHALL grant G4, G5 or G6 authority.
