# Requirements Document

## Introduction

GWC currently resolves one project profile but lacks a typed composition mechanism for gate, agent runtime, environment, and risk profiles. Gate responses also lack a machine-validated trace contract for skills and UTC execution timing.

## Glossary

- **Profile Set**: A typed manifest that composes exactly one gate policy, one environment profile, one risk profile, and one or more agent runtime profiles.
- **Resolver**: A deterministic, fail-closed tool that loads and verifies every referenced profile.
- **Gate Response Trace**: Required response evidence containing skills called and UTC start/end timestamps.

## Requirements

### Requirement 1: Typed Profile Composition

**User Story:** As a GWC operator, I want a profile set to compose typed governance profiles, so that runtime policy is explicit and reusable.

#### Acceptance Criteria

1. WHEN a profile set is active THEN the system SHALL reference exactly one gate policy, one environment profile, one risk profile, and at least one agent runtime profile.
2. WHEN profiles are referenced THEN each reference SHALL contain an explicit ID and repository-relative path.

### Requirement 2: Deterministic Fail-Closed Resolution

**User Story:** As a governance maintainer, I want deterministic profile resolution, so that ambiguous or malformed inputs never silently alter authority.

#### Acceptance Criteria

1. WHEN all references are valid THEN the resolver SHALL return profiles in canonical type and ID order.
2. WHEN a reference is missing, duplicated, unsafe, wrong-type, wrong-ID, inactive, or schema-invalid THEN the resolver SHALL fail without partial success.

### Requirement 3: Standard Gate Policy

**User Story:** As an agent runtime, I want a standard gate policy profile, so that G0-G6 authority remains consistent with canonical GWC contracts.

#### Acceptance Criteria

1. WHEN the standard gate policy is validated THEN it SHALL preserve G0/G1 read-only boundaries, G2 exact approval, G3 Draft PR/evidence behavior, G4 human merge approval, and conditional G5/G6 authority.
2. WHEN G3 passes with current evidence THEN the policy SHALL permit Ready-for-review metadata completion without granting merge authority.

### Requirement 4: Gate Response Traceability

**User Story:** As an auditor, I want every gate response to record execution trace fields, so that skill usage and timing are reviewable.

#### Acceptance Criteria

1. WHEN a gate response trace is emitted THEN it SHALL contain `Skills called`, `Started at UTC`, and `Ended at UTC`.
2. WHEN trace timestamps are validated THEN both SHALL be ISO 8601 UTC values ending in `Z`, and end SHALL NOT precede start.
3. WHEN skills are validated THEN the list SHALL be non-empty, unique, and contain no blank values.

### Requirement 5: Package and Regression Coverage

**User Story:** As a package consumer, I want the resolver assets distributed and tested, so that adoption is reproducible.

#### Acceptance Criteria

1. WHEN the GWC package is built THEN it SHALL include the new profiles, schemas, template, and validators.
2. WHEN tests run THEN they SHALL cover success and fail-closed resolver/trace cases.
