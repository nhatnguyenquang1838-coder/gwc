# Requirements Document

## Introduction

SCRUM-176 advances `intake_context.source-resolution` from a descriptive
read-only catalog node into a typed source-authority boundary. The node must
resolve the active instruction source as `REPO`, `PACKAGE`, or `MIXED`, emit
provenance evidence, and stop closed when source authority is ambiguous.

This spec is additive. It stays inside the existing `intake_context` family,
preserves the `G0_CONTEXT` gate, and does not authorize broader workflow
authority or product runtime behavior.

## Glossary

- **Source resolution:** The bounded classification of the active instruction
  source into `REPO`, `PACKAGE`, or `MIXED`.
- **Source authority:** The highest-confidence instruction source that governs
  the current task context.
- **Provenance evidence:** The verified repository, package, or mixed-source
  inputs that justify the resolved source mode.
- **Typed source result:** A machine-readable record that captures the resolved
  source mode, source authority, provenance evidence, and reason code.
- **Ambiguous source:** A request or context where repository and package
  authority cannot be distinguished deterministically.
- **Exact-head CI:** Validation evidence captured at the exact repository head
  used to derive the spec and later implementation.

## Requirements

### Requirement 1: Deterministic source-mode resolution

**User Story:** As a GWC maintainer, I want `source-resolution` to classify the
active instruction source deterministically, so that the same context always
produces the same result.

#### Acceptance Criteria

1. WHEN `intake_context.source-resolution` receives an equivalent context THEN
   the system SHALL produce the same typed source result.
2. WHEN the active source is repository-only THEN the system SHALL resolve the
   source mode as `REPO`.
3. WHEN the active source is package-only THEN the system SHALL resolve the
   source mode as `PACKAGE`.
4. WHEN both sources are present and intentionally combined THEN the system
   SHALL resolve the source mode as `MIXED`.
5. WHEN source authority cannot be resolved deterministically THEN the system
   SHALL fail closed rather than guessing.

### Requirement 2: Typed provenance evidence and stable reason codes

**User Story:** As an implementation agent, I want the node to expose typed
source provenance and reason codes, so that source authority can be consumed
mechanically instead of relying on prose.

#### Acceptance Criteria

1. WHEN the node contract is updated THEN it SHALL expose machine-readable
   fields for source mode, source authority, provenance evidence, and reason
   codes.
2. WHEN source evidence is incomplete or conflicting THEN the system SHALL emit
   a stable reason code that explains the rejection.
3. WHEN the resolved source is recorded THEN the record SHALL include the
   verified provenance inputs used to reach the decision.
4. WHEN the node remains read-only THEN it SHALL preserve `G0_CONTEXT` and the
   canonical `intake_context` family boundary.

### Requirement 3: Family compatibility and boundary preservation

**User Story:** As a maintainer, I want source resolution to stay inside the
existing `intake_context` family, so that the maturity upgrade does not widen
authority or create a new node family.

#### Acceptance Criteria

1. WHEN the node contract is extended THEN the change SHALL remain inside
   `intake_context.source-resolution`.
2. WHEN the family validator runs THEN it SHALL still accept the full 9-node
   `intake_context` family.
3. WHEN the source resolution contract changes THEN the node SHALL remain
   read-only and `G0_CONTEXT` only.
4. WHEN the requested scope exceeds the family boundary THEN the system SHALL
   reject it rather than widening authority.

### Requirement 4: Validation, negative tests, and exact-head evidence

**User Story:** As a reviewer, I want validation and negative tests for source
resolution, so that the implementation proves deterministic behavior at the
exact repository head.

#### Acceptance Criteria

1. WHEN SCRUM-176 is planned and implemented THEN the task SHALL include an
   evidence snapshot that records the source inputs used to derive the spec.
2. WHEN the validator runs THEN typed source-resolution fields SHALL validate
   successfully while malformed or ambiguous inputs fail closed.
3. WHEN tests are added THEN they SHALL cover repository-only, package-only,
   mixed-source, ambiguous-source, malformed-input, and provenance-evidence
   cases.
4. WHEN validation passes THEN the task SHALL preserve an exact-head CI PASS
   record for the same repository state used to derive the spec.
