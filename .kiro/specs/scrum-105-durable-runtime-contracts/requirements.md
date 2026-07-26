# Requirements Document

## Introduction

SCRUM-105 defines the durable runtime contract needed by the GWC three-node
vertical slice. The deliverable is a versioned contract package, not a
production runtime implementation. It must make replay, suspension, bounded
external writes, and storage replacement explicit without granting any new
GWC authority.

## Glossary

- **Run**: one version-pinned execution instance identified by `run_id`.
- **Event**: an immutable append-only record of a runtime command or outcome.
- **Checkpoint**: the canonical resumable state for the next safe runtime step.
- **CAS**: compare-and-swap using the expected checkpoint revision.
- **Fencing token**: a monotonically increasing lease token that prevents stale
  workers from advancing a run.
- **Pending action**: a durable record of an external operation whose outcome
  is not yet reconciled.
- **Adapter**: the versioned request/result boundary between the runtime and a
  node implementation or external connector.

## Requirements

### Requirement 1: Durable run and event identity

**User Story:** As a runtime operator, I want every run and event bound to the
task, repository, gate, node, actor, and version pins, so that replay evidence
cannot be confused across executions.

#### Acceptance Criteria

1. WHEN a run or event is persisted THEN the contract SHALL require stable
   identifiers, UTC timestamps, runtime/node versions, and repository/task
   binding fields.
2. WHEN an event is appended THEN the contract SHALL require an event sequence
   and predecessor/causal reference sufficient to detect gaps or reordering.
3. The event contract SHALL be append-only and SHALL distinguish pending,
   successful, failed, blocked, expired, rejected, and superseded outcomes.

### Requirement 2: Checkpoint, CAS, lease, and fencing semantics

**User Story:** As a runtime worker, I want an exclusive, revision-checked
resume point, so that concurrent or stale workers cannot advance a run.

#### Acceptance Criteria

1. WHEN a checkpoint is written THEN the store contract SHALL require the
   expected revision and SHALL reject a mismatch without overwriting state.
2. WHEN a worker advances a run THEN the contract SHALL require an unexpired
   lease and the current fencing token.
3. WHEN a lease expires or a token is stale THEN the worker SHALL fail closed
   until the checkpoint is reloaded and live state is reconciled.
4. WHEN a run suspends THEN the checkpoint SHALL record the current node, next
   node, exact next action, gate/approval state, and pending-action references
   before a wait or approval is emitted.

### Requirement 3: Pending action and readback safety

**User Story:** As a bounded-write node, I want unknown external outcomes to be
durable and reconciled, so that retry cannot duplicate an external side effect.

#### Acceptance Criteria

1. WHEN an external action starts THEN the runtime SHALL persist a pending
   action with a stable idempotency key before invoking the adapter.
2. WHEN the adapter result is unknown, timed out, or transport-failed THEN the
   pending action SHALL remain unresolved and the runtime SHALL require a
   readback/reconciliation result before retry or PASS.
3. WHEN readback proves an outcome THEN the store SHALL append the readback
   evidence and close the pending action exactly once.

### Requirement 4: Node request/result adapter contract

**User Story:** As a node author, I want a narrow versioned request/result
   interface, so that nodes can be replaced without changing durable state
   semantics.

#### Acceptance Criteria

1. The request contract SHALL carry run, checkpoint revision, fencing token,
   node version, gate, scope, and idempotency context.
2. The result contract SHALL distinguish success, blocked, retryable failure,
   permanent failure, and unknown external outcome, with evidence references.
3. A side-effect-capable adapter SHALL declare its readback capability and
   SHALL NOT return a terminal success without readback evidence.
4. Version or capability mismatch SHALL be a typed, fail-closed result and
   SHALL NOT silently downgrade the request.

### Requirement 5: Storage portability and migration path

**User Story:** As a platform maintainer, I want the contract to work with the
   SQLite pilot and a future PostgreSQL/Supabase backend, so that storage can be
   replaced without changing runtime semantics.

#### Acceptance Criteria

1. The store interface SHALL define logical operations independently of SQL
   dialect, transaction syntax, or provider-specific client APIs.
2. The migration contract SHALL define additive schema versioning, backfill and
   verification checkpoints, dual-read/dual-write decision points, rollback
   evidence, and cutover readback without authorizing production migration.
3. Provider-specific configuration, credentials, production data, and live
   migration execution SHALL be explicitly out of scope.

### Requirement 6: Contract validation and package traceability

**User Story:** As a maintainer, I want automated contract checks, so that the
   runtime package cannot advance with incomplete or contradictory schemas.

#### Acceptance Criteria

1. WHEN the contract test suite runs THEN it SHALL validate each new schema,
   representative valid instances, rejection cases, and cross-contract
   invariants.
2. The package manifest SHALL export each canonical schema, contract document,
   validator/test entry, and a release fragment with stable IDs.
3. The deliverable SHALL not implement a scheduler, worker, database migration,
   deployment, production configuration, credential access, or production-data
   operation.
