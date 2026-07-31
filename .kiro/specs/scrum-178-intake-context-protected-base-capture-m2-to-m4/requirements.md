# Requirements Document

## Introduction

SCRUM-178 advances `intake_context.protected-base-capture` from a descriptive
read-only catalog node into a typed protected-base evidence boundary. The node
must capture the exact protected-base SHA as immutable evidence, support
deterministic readback, and reject stale-base or drifted evidence.

This spec is additive. It stays inside the existing `intake_context` family,
preserves the `G0_CONTEXT` gate, and does not authorize broader workflow
authority or product runtime behavior.

## Glossary

- **Protected base:** The exact repository commit treated as the immutable base
  for gate, plan, and PR evidence.
- **Readback:** The deterministic verification that the captured protected-base
  SHA matches the verified source of truth.
- **Drift:** A change between the captured protected base and the verified base
  used by the current task context.
- **Typed base evidence:** A machine-readable record that captures the protected
  base SHA, evidence source, readback status, drift state, and reason code.
- **Stale base:** A protected-base value that no longer matches the verified
  source of truth for the current task.
- **Exact-head CI:** Validation evidence captured at the exact repository head
  used to derive the spec and later implementation.

## Requirements

### Requirement 1: Deterministic protected-base capture

**User Story:** As a GWC maintainer, I want `protected-base-capture` to capture
the protected base deterministically, so that the same repository state always
produces the same typed base evidence.

#### Acceptance Criteria

1. WHEN `intake_context.protected-base-capture` receives an equivalent
   repository state THEN the system SHALL produce the same typed base evidence.
2. WHEN the protected base can be verified from the current source of truth THEN
   the system SHALL record the exact protected-base SHA.
3. WHEN the protected base cannot be resolved deterministically THEN the system
   SHALL fail closed rather than guessing.
4. WHEN a protected-base value is captured THEN the record SHALL be immutable
   for the task context.

### Requirement 2: Typed readback and stale-base rejection

**User Story:** As an implementation agent, I want the node contract to expose
typed readback and stale-base rejection evidence, so that governance can consume
the result mechanically instead of relying on prose.

#### Acceptance Criteria

1. WHEN the node contract is updated THEN it SHALL expose machine-readable
   fields for protected-base SHA, evidence source, readback status, drift state,
   and reason codes.
2. WHEN the readback SHA does not match the verified source of truth THEN the
   system SHALL reject the context with a stable reason code.
3. WHEN the protected base is stale or drifted THEN the system SHALL reject the
   context with a stable reason code.
4. WHEN the node remains read-only THEN it SHALL preserve `G0_CONTEXT` and the
   canonical `intake_context` family boundary.

### Requirement 3: Family compatibility and boundary preservation

**User Story:** As a maintainer, I want protected-base capture to stay inside
the existing `intake_context` family, so that the maturity upgrade does not
widen authority or create a new node family.

#### Acceptance Criteria

1. WHEN the node contract is extended THEN the change SHALL remain inside
   `intake_context.protected-base-capture`.
2. WHEN the family validator runs THEN it SHALL still accept the full 9-node
   `intake_context` family.
3. WHEN the protected-base contract changes THEN the node SHALL remain read-only
   and `G0_CONTEXT` only.
4. WHEN the requested scope exceeds the family boundary THEN the system SHALL
   reject it rather than widening authority.

### Requirement 4: Validation, schema, and exact-head evidence

**User Story:** As a reviewer, I want validation and negative tests for
protected-base capture, so that the implementation proves deterministic stale
base rejection at the exact repository head.

#### Acceptance Criteria

1. WHEN SCRUM-178 is planned and implemented THEN the task SHALL include an
   evidence snapshot that records the source inputs used to derive the spec.
2. WHEN the validator runs THEN typed protected-base fields SHALL validate
   successfully while stale or mismatched inputs fail closed.
3. WHEN tests are added THEN they SHALL cover deterministic readback, drift
   detection, schema rejection, stale-base rejection, malformed-input, and
   evidence-retention cases.
4. WHEN validation passes THEN the task SHALL preserve an exact-head CI PASS
   record for the same repository state used to derive the spec.
