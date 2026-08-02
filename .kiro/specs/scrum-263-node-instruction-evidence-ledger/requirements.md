# Requirements Document

## Introduction

SCRUM-263 hardens GWC Node Architect so every route-selected executable node has a validated instruction contract, emits canonical task-scoped runtime evidence, and resolves a deterministic next node/action/gate without acquiring gate authority.

## Glossary

- **Node instruction card**: machine-readable node-specific contract consumed before execution.
- **Evidence ledger**: canonical task/run/node scoped records for start, decision, result, readback, checkpoint, runtime events, digests, and next-route selection.
- **Authority plane**: GWC gate evidence and exact human approvals.
- **Execution plane**: Node Architect route resolution and node execution.
- **Workflow mode**: normal, fastlane, e2e, hotfix, or rescue execution strategy.

## Requirements

### Requirement 1: Node Instruction Contract

**User Story:** As a governed agent, I want a complete instruction card for each executable node, so that execution is deterministic and reviewable.

#### Acceptance Criteria

1. WHEN a node is selected THEN the system SHALL load a card containing `node_id`, `gate`, `purpose`, `entry_conditions`, `inputs`, `allowed_actions`, `forbidden_actions`, `outputs`, `evidence_required`, `logs_required`, `next`, `retry`, `rollback`, and `authority_boundary`.
2. WHEN a required card or field is absent THEN execution SHALL fail closed with a stable failure code.

### Requirement 2: Cross-Source Validation

**User Story:** As a governance maintainer, I want instruction cards bound to registry, descriptor, route, and gate data, so that drift cannot create an executable mismatch.

#### Acceptance Criteria

1. WHEN validating a card THEN `node_id` SHALL match the route, descriptor, and node registry.
2. WHEN validating a card THEN allowed gates SHALL match descriptor and active route gates.
3. WHEN implementation or maturity requirements are unmet THEN execution SHALL remain blocked.

### Requirement 3: Evidence and Log Contract

**User Story:** As an auditor, I want every node run to emit canonical evidence and logs, so that replay and review do not depend on chat history.

#### Acceptance Criteria

1. WHEN a node executes THEN the ledger SHALL emit `node-start`, `node-decision`, `node-result`, `node-readback`, `checkpoint`, `runtime-event`, `decision_digest`, `state_digest`, `event_digest`, and `next-route decision` evidence.
2. WHEN evidence or log requirements are missing THEN execution SHALL fail closed before effectful action.
3. WHEN records are emitted THEN paths SHALL be task/run/node scoped under `.gwc/tasks/<task-id>/node-runtime/...`.

### Requirement 4: Next-Route Completeness

**User Story:** As an orchestrator, I want pass, blocked, pending, and retry outcomes mapped, so that an agent always knows the next legal action.

#### Acceptance Criteria

1. WHEN an applicable outcome lacks `next_node`, `next_action`, or `next_gate` THEN validation SHALL return `NODE_NEXT_ROUTE_MISSING`.
2. WHEN the G2 scoped-write path passes THEN the next gate SHALL resolve to `G3_PR` without granting PR authority.

### Requirement 5: Authority Separation

**User Story:** As the human authority holder, I want node contracts and route decisions unable to grant later-gate authority, so that automation cannot escalate itself.

#### Acceptance Criteria

1. Node instructions SHALL explicitly deny independent G2/G3/G4/G5/G6 authority.
2. Merge, deploy, release, production configuration/data, credentials, secrets, and migrations SHALL remain separately gated.
3. Any authority-escalating flag SHALL fail with `NODE_AUTHORITY_ESCALATION_ATTEMPT`.

### Requirement 6: Mode Invariant

**User Story:** As a GWC operator, I want normal, fastlane, e2e, hotfix, and rescue modes to use the same node runtime boundary, so that acceleration cannot bypass evidence or authority.

#### Acceptance Criteria

1. Every listed workflow mode SHALL require boot, claim intake, gate authority, route resolution, instruction validation, evidence/log recording, and next-route resolution.
2. Any bypass configuration SHALL fail with `MODE_BYPASSES_NODE_RUNTIME`.

### Requirement 7: Replay, Retry, and Rollback

**User Story:** As a recovery operator, I want node instructions to define replay and rollback behavior, so that retries do not duplicate effects.

#### Acceptance Criteria

1. Retry rules SHALL define idempotency identity, replay checks, retry limits, and pending reconciliation behavior.
2. Rollback rules SHALL distinguish reversible local effects, reconciliation, and human-required recovery.

### Requirement 8: G2 Repository-Write Vertical Slice

**User Story:** As a delivery agent, I want the G2 write route covered end-to-end, so that the first universal runtime path is executable and testable.

#### Acceptance Criteria

1. The validated route SHALL cover `gate_authority.gate-state-resolution` → `repo_delivery.scoped-file-write` → `repo_delivery.diff-readback` → `gate_authority.gate-transition-decision` → `G3_PR`.
2. Each node in the route SHALL have a valid instruction card and evidence/log/next contract.

### Requirement 9: Projection Boundaries

**User Story:** As a governance owner, I want Jira, Slack, and Notion to remain projection-only, so that communication systems cannot replace canonical repository evidence.

#### Acceptance Criteria

1. Projection readbacks MAY be logged but SHALL NOT satisfy gate authority or node runtime evidence requirements.

### Requirement 10: Regression Tests

**User Story:** As a maintainer, I want fail-closed tests for all required gaps and modes, so that future changes cannot silently weaken the invariant.

#### Acceptance Criteria

1. Tests SHALL prove missing instruction, evidence, logs, and next routes fail closed.
2. Tests SHALL prove node instructions cannot grant merge/deploy/production authority.
3. Tests SHALL prove fastlane, e2e, hotfix, and rescue modes still require node runtime.
4. Tests SHALL prove the G2 scoped-write path validates instruction, evidence, logs, and next route.
