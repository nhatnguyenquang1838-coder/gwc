# Requirements Document

## Introduction

SCRUM-284 adds the missing governed bridge from a Human-approved Node Research recommendation to a separately tracked execution task and then into the existing GWC autonomous delivery runtime. The bridge must be deterministic, replay-safe, idempotent across Jira/GitHub projections, lane-preserving, and unable to elevate research approval into merge/deploy/production authority.

## Glossary

- **Research Record**: A Jira/GitHub tracking record containing a Node Architect research result and implementation recommendation.
- **Research Execution Approval**: Human authority binding an exact research digest and approved implementation round/scope.
- **ExecutionTaskSpec**: Canonical provider-neutral specification compiled from the approved research subset.
- **Materialization Key**: Deterministic identity used to reconcile/upsert paired execution tracking records.
- **Execution Projection**: Jira/GitHub work-tracking representation; never canonical governance authority.
- **Child G2/G3 Authority**: Task-scoped G2 execution and G3 Draft-PR authority projected as strict subsets of the exact Human research execution approval; never merge authority.
- **G4 Boundary**: Mandatory Human merge authority after G3 delivery/readiness.

## Requirements

### Requirement 1: Bound Research Approval

**User Story:** As a Human approver, I want research execution approval bound to exact research evidence and scope, so that later automation cannot reinterpret or broaden my approval.

#### Acceptance Criteria

1. WHEN approval is evaluated THEN the system SHALL bind research reference, research digest, repository, approved round/scope, scope hash, risk ceiling, expiry, and approval identity.
2. WHEN the research content or approved scope drifts after approval THEN the system SHALL reject execution materialization.
3. Research execution approval SHALL NOT grant G4, G5, or G6 authority.
4. Research execution approval MAY delegate bounded task-scoped G2 and G3 actions only when those child-gate capabilities are explicitly listed in the signed/approved parent scope.

### Requirement 2: Deterministic Approved-Research Selection

**User Story:** As an autonomous runner, I want to select only approved research from the active lane, so that scheduled and immediate triggers behave identically and do not switch lanes.

#### Acceptance Criteria

1. WHEN given the same canonical research snapshot and policy THEN immediate and scheduled triggers SHALL select the same eligible research.
2. The selector SHALL preserve the active lane and excluded lanes.
3. The selector SHALL reject research whose required dependencies are semantically cancelled, refinement-only, superseded, no-deliverable, missing repository implementation, or missing exact-SHA evidence.

### Requirement 3: Idempotent Execution Task Materialization

**User Story:** As an autonomous runner, I want paired GitHub and Jira execution tasks to be upserted idempotently, so that retries and crashes cannot duplicate work.

#### Acceptance Criteria

1. The system SHALL derive one deterministic materialization key from approved research identity, approved digest/scope, target repository, and authority revision.
2. WHEN matching GitHub and Jira projections already exist THEN the system SHALL reuse them.
3. WHEN only one projection exists THEN the system SHALL create/reconcile only the missing projection.
4. WHEN conflicting identities exist for the same materialization key THEN the system SHALL fail closed and SHALL NOT create a third projection.
5. Restart after a partial effect SHALL resume from durable evidence without duplicate create or claim.

### Requirement 4: Provider-Neutral ExecutionTaskSpec

**User Story:** As a GWC runtime, I want a canonical execution spec derived from the approved research subset, so that AI/task execution does not consume unconstrained research prose as authority.

#### Acceptance Criteria

1. The ExecutionTaskSpec SHALL contain origin research refs, approved digest/scope, repository/base binding, objective, implementation guidance, acceptance criteria, dependencies, risks/exclusions, materialization key, projection identities, and child-G2 derivation inputs.
2. Research prose outside the explicitly approved scope SHALL remain data and SHALL NOT expand executable intent.
3. The same approved inputs SHALL produce the same semantic task spec and materialization identity.

### Requirement 5: Bounded Child G2/G3 and Existing Runtime Reuse

**User Story:** As a governance owner, I want execution to enter the existing GWC gate/runtime path, so that this feature does not create a parallel authority plane.

#### Acceptance Criteria

1. The system SHALL derive task-scoped G2 only when repository, paths/actions, risk, approved scope/round, and expiry are subsets of the parent authority.
2. The system SHALL derive bounded G3 authority only for Draft PR creation/update, exact-head CI/review closure, and ready-for-review metadata when these actions are explicitly included in the parent Human research-execution approval.
3. A parent approval that omits G3 delegation SHALL stop at the G3 Human boundary instead of silently broadening authority.
4. After claim the flow SHALL reuse normal G0/G1/G2/G3, checkpoint, evidence, AI execution, CI and continuation primitives.
5. The flow SHALL NOT bypass Node Architect instruction/evidence runtime.

### Requirement 6: Autonomous E2E Delivery Through G3

**User Story:** As a Human approver, I want an approved research implementation to proceed autonomously to a validated PR, so that I only need to intervene at the merge authority boundary unless a blocker occurs.

#### Acceptance Criteria

1. WHEN child G2 is valid THEN the flow SHALL execute scoped implementation, validation, guarded branch push, Draft PR creation/update, exact-head CI monitoring, bounded authorized repair, and independent G3 review.
2. WHEN a repair changes head SHA THEN prior exact-head CI/review evidence SHALL be invalidated and rechecked.
3. WHEN the parent approval delegates bounded G3 and G3 passes THEN the flow SHALL stop at HUMAN_AUTHORITY_REQUIRED for exact G4 merge approval.
4. The flow SHALL NOT auto-merge, deploy, release, modify production configuration/data, rotate credentials, or run migrations.

### Requirement 7: Controlled Post-81 Node Extension

**User Story:** As a Node Architect maintainer, I want the new executable node added without rewriting the historical 81-node rollout contract or stealing a semantically unrelated slot, so that registry evolution remains explicit and auditable.

#### Acceptance Criteria

1. The historical `REVAMP-GWC-015` 81-node expansion plan SHALL remain unchanged as baseline/history.
2. The implementation SHALL define a versioned post-81 extension contract/registry that authorizes explicitly G1-approved nodes beyond the original baseline.
3. The new executable node SHALL use a stable ID under an existing compatible family, recommended `gate_authority.research-review-to-execution`, and SHALL NOT repurpose an unrelated planned slot.
4. Runtime registry/schema/graph validators SHALL preserve the original 81 baseline identities while validating explicitly admitted extension nodes.
5. Registry migration SHALL fail closed on undeclared extension nodes, duplicate slots/IDs, provenance mismatch, family drift, or graph/profile references to unknown nodes.
6. This task SHALL add only the one SCRUM-284 node extension; it SHALL NOT reopen broad 81-node catalog expansion.

### Requirement 8: Durable Trigger and Recovery Semantics

**User Story:** As an operator, I want immediate and scheduler-triggered runs to share one durable flow, so that trigger timing cannot change semantics or authority.

#### Acceptance Criteria

1. `immediate_after_approval` and `scheduled_poll` SHALL call the same selection/materialization semantics.
2. Trigger source SHALL NOT grant authority.
3. Duplicate dispatch SHALL be fenced.
4. Projection failure SHALL produce late-reconciliation evidence rather than false success.
