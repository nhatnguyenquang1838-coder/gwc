# Requirements Document

## Introduction

DS MCP already provides durable workflows, task claims, leases, GitHub operations, CI handling, agent heartbeat, retries, and audit events. The missing Pilot v1 capability is a distinct QA stage with role-bound ownership and exact PR/head-SHA evidence.

This spec adds the minimum control-plane behavior needed to run a real Lead-to-Dev-to-QA pilot against Rental Home. It extends the existing State Engine and does not replace it with a new orchestrator.

Non-goals:

- No merge, auto-merge, deployment, release, production configuration, credential, migration, or production-data authority.
- No generic DAG engine in Pilot v1.
- No Jira or Linear integration.
- No replacement of GWC gates or GitHub guarded-write controls.

## Glossary

| Term | Definition |
|---|---|
| Hub | DS MCP control plane and DS Admin runtime state |
| Spoke | A project repository and local agent runtime |
| Lead Agent | Agent that inspects, plans, and creates bounded workflow tasks |
| Dev Agent | Agent permitted to execute implementation and repair stages |
| QA Agent | Agent permitted to validate an exact PR head and submit QA evidence |
| Reviewer | Human or separately authorized reviewer that accepts or returns work |
| Runtime SSOT | DS Admin/AgentOps state for claims, leases, stages, PR, CI, and QA |
| Spec SSOT | Repository Kiro spec for requirements, design, and static task definition |
| QA Evidence | Structured validation result bound to repository, PR, and exact head SHA |
| G4 | Separate human merge authority |
| Pilot Run | One complete workflow instance with a root task and auditable stage tasks |

## Requirements

### Requirement 1: Pilot Workflow Stage Model

**User Story:** As a Lead, I want a distinct QA stage after CI, so that Dev and QA responsibilities are auditable and separated.

#### Acceptance Criteria

1. WHEN a `create_pr` task succeeds THEN the system SHALL create or enter the existing `wait_github_ci` stage.
2. WHEN CI succeeds for the exact repository, PR, and head SHA THEN the system SHALL create a `qa_validate` task.
3. WHEN CI fails THEN the system SHALL route to the existing bounded repair path.
4. WHEN QA passes THEN the system SHALL route to `final_report` or `review_ready`.
5. WHEN QA fails THEN the system SHALL return work to a Dev-capable repair stage with the QA findings attached.
6. THE system SHALL NOT mark the workflow complete solely because CI passed.

### Requirement 2: Role Capability Enforcement

**User Story:** As an operator, I want each agent role limited to allowed stages, so that a worker cannot self-assign privileged work.

#### Acceptance Criteria

1. WHEN an agent claims a task THEN the system SHALL verify the registered role and advertised capability.
2. A Lead Agent SHALL be allowed to claim `analyze_repo` and `plan_changes`.
3. A Dev Agent SHALL be allowed to claim `modify_code`, `fix_ci`, and approved implementation-repair stages.
4. A QA Agent SHALL be allowed to claim `qa_validate`.
5. A normal worker SHALL NOT create the next State Engine task directly.
6. IF role or capability does not match THEN the system SHALL reject the claim with a stable reason code and audit event.

### Requirement 3: Exact Work-Item Binding

**User Story:** As a project owner, I want execution bound to the approved task and repository scope, so that an agent cannot work on the wrong repository or branch.

#### Acceptance Criteria

1. WHEN a targeted claim is supplied THEN the system SHALL match task ID, workflow ID, repository, branch, and PR fields when present.
2. THE system SHALL NOT fall back to an unrelated capability-only task when targeted filters are supplied.
3. BEFORE task result submission the system SHALL verify task ownership and active lease.
4. BEFORE PR or QA state acceptance the system SHALL verify repository, PR number, and exact head SHA.
5. IF any binding mismatches THEN the system SHALL fail closed with an auditable stable reason code.

### Requirement 4: Structured QA Evidence

**User Story:** As a Reviewer, I want machine-readable QA evidence tied to the exact code revision, so that I can trust the validation result.

#### Acceptance Criteria

1. WHEN QA submits a result THEN the system SHALL validate a versioned `QaEvidence` payload.
2. `QaEvidence` SHALL include workflow ID, task ID, repository, PR number, head SHA, QA agent ID, commands, checks, result, findings, and timestamps.
3. THE system SHALL reject QA evidence for a stale or different head SHA.
4. THE system SHALL store accepted QA evidence in task artifacts and event history.
5. THE system SHALL preserve sanitized human-readable summaries.
6. QA evidence SHALL NOT grant G4 merge, G5 deployment, or G6 production authority.

### Requirement 5: Bounded Failure Recovery

**User Story:** As an operator, I want bounded repair loops, so that agents cannot retry indefinitely.

#### Acceptance Criteria

1. WHEN CI or QA fails for a repository-fixable reason THEN the system SHALL create a bounded Dev repair task.
2. THE system SHALL allow no more than three automatic repair attempts.
3. THE system SHALL allow no more than one repeated attempt for an unchanged root cause.
4. WHEN the repair budget is exhausted THEN the system SHALL set `needs_attention` and require human intervention.
5. EACH attempt SHALL be represented in the event log with the old and new head SHA where applicable.

### Requirement 6: Operational Liveness

**User Story:** As an operator, I want agent liveness and lease state visible, so that stalled work is detectable.

#### Acceptance Criteria

1. WHEN an agent is active THEN it SHALL publish periodic heartbeat records.
2. WHEN a heartbeat becomes stale THEN the dashboard SHALL expose the agent as stale or offline.
3. WHEN a task lease expires THEN the scheduler SHALL recover, requeue, or dead-letter it according to policy.
4. THE system SHALL expose current stage, owner, lease expiry, queue depth, CI state, and QA state.
5. A stale agent SHALL NOT retain effective write authority after lease expiry.

### Requirement 7: Runtime Source of Truth

**User Story:** As a Tech PM, I want one runtime source of truth, so that Task Server and repository Markdown cannot report conflicting execution states.

#### Acceptance Criteria

1. Pilot workflows SHALL use `tracking_mode: ds_admin_runtime`.
2. DS Admin SHALL be canonical for stage, owner, claim, lease, PR, CI, QA, and blocker state.
3. Repository specs SHALL remain canonical for requirements and design.
4. Repository task boards MAY be generated projections but SHALL NOT override Pilot runtime state.
5. State changes SHALL use State Engine operations only.

### Requirement 8: API, MCP, and Dashboard Projection

**User Story:** As an agent or operator, I want consistent read surfaces, so that the same workflow state is visible through REST, MCP, and dashboard.

#### Acceptance Criteria

1. REST and MCP SHALL expose the current Pilot stage and exact task binding.
2. REST and MCP SHALL expose accepted QA evidence metadata without secrets or unbounded logs.
3. Dashboard SHALL identify `needs_attention` reasons.
4. Public capability documentation SHALL list the new stage and payload versions.
5. Sensitive state-changing routes SHALL remain protected by existing route policy, auth, role, rate-limit, and request-ID controls.

### Requirement 9: Pilot Auditability

**User Story:** As a governance reviewer, I want a complete event trail, so that each action can be reconstructed.

#### Acceptance Criteria

1. EACH claim, lease, result, transition, PR binding, CI event, QA submission, and repair attempt SHALL create an audit event.
2. Audit events SHALL include workflow ID, task ID, actor, event type, timestamp, and bounded metadata.
3. Secret values and raw credentials SHALL NOT be recorded.
4. The final report SHALL identify all stage tasks, PR/head SHAs, CI results, QA result, retries, residual risks, and excluded authorities.

### Requirement 10: Validation and Compatibility

**User Story:** As a maintainer, I want the Pilot capability tested without breaking existing workflows, so that current DS MCP behavior remains stable.

#### Acceptance Criteria

1. Existing async workflows without `qa_validate` SHALL continue to work or SHALL be migrated through an explicit versioned workflow template.
2. Unit tests SHALL cover role policy, targeted claims, stage transitions, stale-head QA evidence, retry exhaustion, and audit events.
3. Integration-style tests SHALL cover the success path and controlled QA failure-recovery path.
4. `npm test`, `npm run typecheck`, and `npm run build` SHALL pass before Draft PR delivery.
5. THE implementation SHALL NOT expose merge, branch deletion, force-push, secret-management, deployment, or production-data operations.
