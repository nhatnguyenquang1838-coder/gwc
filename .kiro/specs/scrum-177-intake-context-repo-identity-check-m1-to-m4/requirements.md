# Requirements Document

## Introduction

SCRUM-177 advances `intake_context.repo-identity-check` from a descriptive
read-only catalog node into a typed repository-identity boundary. The node must
validate repository identity, default branch, protected branch, and execution
mode assumptions while failing closed on mismatch.

This spec is additive. It stays inside the existing `intake_context` family,
preserves the `G0_CONTEXT` gate, and does not authorize broader workflow
authority or product runtime behavior.

## Glossary

- **Repository identity:** The verified repository owner/name or equivalent
  canonical repository identifier used by the current task context.
- **Default branch:** The repository branch that the workspace recognizes as the
  default branch for source-of-truth checks.
- **Protected branch:** A branch that is not writable through uncontrolled
  mutation and must be honored by governance before any write-capable step.
- **Execution mode:** The current agent execution posture, such as
  `chat_connector_only` or `local_agent`, as observed by the governance layer.
- **Typed identity result:** A machine-readable record that captures the
  validated repository identity, default branch, protected branch, execution
  mode, and reason code.
- **Mismatch:** A condition where repository identity, branch identity, or
  execution-mode assumptions diverge from the verified source of truth.

## Requirements

### Requirement 1: Deterministic repository-identity validation

**User Story:** As a GWC maintainer, I want `repo-identity-check` to validate
repository identity deterministically, so that the same repository state always
produces the same typed identity result.

#### Acceptance Criteria

1. WHEN `intake_context.repo-identity-check` receives an equivalent repository
   state THEN the system SHALL produce the same typed identity result.
2. WHEN the repository identity matches the verified target THEN the system
   SHALL resolve the identity as accepted.
3. WHEN the repository identity does not match the verified target THEN the
   system SHALL fail closed rather than guessing.
4. WHEN repository identity cannot be resolved deterministically THEN the
   system SHALL emit a stable reason code.

### Requirement 2: Typed branch and execution-mode evidence

**User Story:** As an implementation agent, I want the node contract to expose
typed branch and execution-mode evidence, so that governance can consume it
mechanically instead of relying on prose.

#### Acceptance Criteria

1. WHEN the node contract is updated THEN it SHALL expose machine-readable
   fields for repository identity, default branch, protected branch, execution
   mode, and reason codes.
2. WHEN default-branch or protected-branch assumptions are inconsistent THEN the
   system SHALL reject the context with a stable reason code.
3. WHEN the execution mode is not recognized or is inconsistent with the
   verified environment THEN the system SHALL reject the context with a stable
   reason code.
4. WHEN the node remains read-only THEN it SHALL preserve `G0_CONTEXT` and the
   canonical `intake_context` family boundary.

### Requirement 3: Family compatibility and boundary preservation

**User Story:** As a maintainer, I want repository identity checks to stay
inside the existing `intake_context` family, so that the maturity upgrade does
not widen authority or create a new node family.

#### Acceptance Criteria

1. WHEN the node contract is extended THEN the change SHALL remain inside
   `intake_context.repo-identity-check`.
2. WHEN the family validator runs THEN it SHALL still accept the full 9-node
   `intake_context` family.
3. WHEN the identity contract changes THEN the node SHALL remain read-only and
   `G0_CONTEXT` only.
4. WHEN the requested scope exceeds the family boundary THEN the system SHALL
   reject it rather than widening authority.

### Requirement 4: Validation, mismatch rejection, and exact-head evidence

**User Story:** As a reviewer, I want validation and negative tests for
repository identity, so that the implementation proves deterministic mismatch
rejection at the exact repository head.

#### Acceptance Criteria

1. WHEN SCRUM-177 is planned and implemented THEN the task SHALL include an
   evidence snapshot that records the source inputs used to derive the spec.
2. WHEN the validator runs THEN typed repository-identity fields SHALL validate
   successfully while mismatched or incomplete inputs fail closed.
3. WHEN tests are added THEN they SHALL cover repository identity mismatch,
   default-branch mismatch, protected-branch mismatch, execution-mode mismatch,
   malformed-input, and evidence-retention cases.
4. WHEN validation passes THEN the task SHALL preserve an exact-head CI PASS
   record for the same repository state used to derive the spec.
