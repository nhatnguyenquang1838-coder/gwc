# Requirements Document

## Introduction

SCRUM-210 adds a deterministic, replay-safe cleanup primitive for expired, disposable runtime-checkpoint hints and interrupt frames. It must preserve governance, audit, and append-only evidence and it must never contact external services.

## Glossary

- **Disposable entry**: a `resume-hint` or `interrupt-frame` with `retention_class: disposable`.
- **Tombstone**: an auditable marker that neutralizes an eligible entry without deleting retained evidence.
- **Active resume**: an unexpired resume token bound to one registry entry; it takes priority over cleanup.
- **Replay-safe**: repeated evaluation of identical state and policy produces equivalent deterministic evidence.

## Requirements

### Requirement 1: Deterministic cleanup classification

**User Story:** As a runtime operator, I want expired disposable checkpoint hints classified deterministically, so that retries do not create inconsistent cleanup outcomes.

#### Acceptance Criteria

1. WHEN a disposable `resume-hint` or `interrupt-frame` has reached its expiry time THEN the system SHALL select it for tombstoning.
2. WHEN a disposable entry has not reached expiry THEN the system SHALL retain it.
3. WHEN the same registry and policy are evaluated repeatedly THEN the selected tombstone and retain sets SHALL have the same canonical digest.

### Requirement 2: Evidence preservation

**User Story:** As a governance auditor, I want governance, audit, and append-only evidence protected from cleanup, so that expiry handling cannot erase auditability.

#### Acceptance Criteria

1. WHEN an entry has retention class `governance` or `audit` THEN the system SHALL retain it regardless of expiry metadata.
2. WHEN an entry is an append-only `runtime-event` or retained evidence type THEN the system SHALL NOT tombstone it.
3. WHEN cleanup selects an entry THEN the system SHALL emit an auditable tombstone marker and preserve the resulting registry.

### Requirement 3: Active resume priority

**User Story:** As a recovering worker, I want a valid active resume path retained, so that concurrent expiry cleanup cannot interrupt recovery.

#### Acceptance Criteria

1. WHEN the active resume entry has an unexpired resume token THEN the system SHALL retain it even if its disposable hint has expired.
2. WHEN that resume token has expired THEN the system SHALL allow normal expiry classification.

### Requirement 4: Local and portable validation

**User Story:** As a maintainer, I want a local data-oriented implementation with portable tests, so that behavior is reproducible without connector access.

#### Acceptance Criteria

1. WHEN the module executes THEN it SHALL NOT call GitHub, Jira, Slack, or a production service.
2. WHEN the focused test runs as a direct file or through unittest discovery under Python 3.11 THEN it SHALL pass without resolving a host-level `tools` package.
3. WHEN malformed CLI JSON or invalid dataclass input is supplied THEN the command SHALL fail locally without emitting an external side effect.

### Requirement 5: Node catalog registration

**User Story:** As a Node Architect consumer, I want the cleanup primitive represented by its canonical catalog descriptor, so that it can be discovered under the runtime-checkpoint family without adding orchestration behavior.

#### Acceptance Criteria

1. WHEN the catalog is inspected THEN it SHALL contain `runtime_checkpoint.checkpoint-expiry-cleanup` with canonical status and `g2_required` authority boundary.
2. WHEN the descriptor is verified during delivery THEN it SHALL remain metadata-only and SHALL NOT schedule, invoke, or deploy the cleanup primitive.
