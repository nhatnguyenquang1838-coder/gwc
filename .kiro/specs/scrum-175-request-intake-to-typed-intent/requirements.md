# Requirements Document

## Introduction

SCRUM-175 upgrades `intake_context.request-intake` from a descriptive G0 context node into a deterministic typed intake boundary. The node must normalize a user request into machine-readable intent, outcome, constraints, exclusions, entry guards, and stable reason codes while preserving the existing `G0_CONTEXT` and read-only authority boundary.

This spec is additive. It does not authorize broader gate access, production runtime behavior, or a new node family.

## Glossary

- **Typed intake:** A normalized, machine-readable request record with explicit fields for intent, outcome, constraints, exclusions, entry guards, and reason codes.
- **Entry guard:** A precondition that must be satisfied before intake can be considered valid.
- **Reason code:** A stable machine-readable code that explains why intake was accepted, normalized, or rejected.
- **Evidence snapshot:** The bounded artifact set that records the exact source inputs, derived contract, and validation outcome for the task.
- **Exact-head CI:** Validation and test evidence captured at the exact repository head used to derive the spec and implementation plan.
- **Canonical request:** The request shape that the repository treats as the authoritative normalization input for this node family.

## Requirements

### Requirement 1: Deterministic request normalization

**User Story:** As a GWC maintainer, I want `request-intake` to normalize requests deterministically, so that the same request always produces the same typed intake record.

#### Acceptance Criteria

1. WHEN `intake_context.request-intake` receives an equivalent request input THEN the system SHALL produce the same normalized typed intake output.
2. WHEN the request input is semantically unchanged but formatted differently THEN the system SHALL normalize it to the same typed intake record.
3. WHEN the request contains ambiguous intent or conflicting scope signals THEN the system SHALL fail closed rather than guessing.
4. WHEN the request cannot be normalized deterministically THEN the system SHALL emit a stable reason code.

### Requirement 2: Machine-readable intake contract and guardrails

**User Story:** As an implementation agent, I want the node contract to expose typed fields and validation guards, so that intake can be consumed mechanically instead of relying on prose.

#### Acceptance Criteria

1. WHEN the node contract is updated THEN it SHALL expose machine-readable fields for intent, outcome, constraints, exclusions, entry guards, and reason codes.
2. WHEN the node contract is consumed by the validator THEN the validator SHALL continue to enforce `G0_CONTEXT` only and read-only authority.
3. WHEN malformed input is supplied THEN the system SHALL reject it with a stable reason code.
4. WHEN the requested scope exceeds the node family boundary THEN the system SHALL reject it rather than widening authority.

### Requirement 3: Evidence snapshot and generated runbook

**User Story:** As a reviewer, I want a bounded evidence snapshot and generated runbook for this task, so that the implementation can be audited from the exact source state.

#### Acceptance Criteria

1. WHEN SCRUM-175 is planned and implemented THEN the task SHALL include an evidence snapshot that records the source inputs used to derive the spec.
2. WHEN the task is validated THEN the implementation SHALL preserve an exact-head validation record.
3. WHEN the task is handed off THEN the plan SHALL include a generated runbook or run-summary artifact that describes the validation commands and exclusions.
4. WHEN evidence is incomplete THEN the task SHALL remain blocked instead of claiming validation success.

### Requirement 4: Validation and compatibility

**User Story:** As a maintainer, I want existing intake-context validation to remain intact, so that the new typed contract does not break the current family boundary.

#### Acceptance Criteria

1. WHEN the family validator runs THEN it SHALL still accept the real nine-node `intake_context` family.
2. WHEN a node widens its authority boundary or gate membership THEN the validator SHALL reject it.
3. WHEN the new typed intake contract is added THEN regression tests SHALL cover canonical input, malformed input, ambiguous input, and deterministic normalization.
4. WHEN validation passes THEN the task SHALL remain confined to the existing `intake_context` family and SHALL NOT create a parallel node family.

