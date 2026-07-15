# Requirements Document

## Introduction

The end-state is a governed, distributed, asynchronous multi-agent SDLC control plane that supports multiple repositories and local agent runtimes while preserving exact task ownership, evidence, and human authority.

DS MCP remains the Hub. Project repositories and local IDE agents remain Spokes. GWC remains the gate and authority contract. Repository specs remain the requirements/design source. DS Admin remains the runtime execution source.

Pilot v1 is the first compatibility slice, not the final architecture.

Non-goals:

- No unrestricted autonomous merge, deploy, production configuration, credential, migration, or production-data authority.
- No replacement of repository-specific engineering conventions.
- No requirement that all agents use the same IDE or AI model.
- No central storage of source-code workspaces.
- No hidden or unverifiable agent execution.

## Glossary

| Term | Definition |
|---|---|
| Workflow Template | Versioned declarative definition of stages, roles, transitions, gates, retry, and evidence |
| Workflow Run | One execution instance of a workflow template |
| Stage Task | Claimable unit owned by one role/agent with one lease |
| Project Adapter | Repository-specific contract for commands, evidence, spec projection, and boundaries |
| Policy Pack | Versioned role, gate, QA, security, and retry rules |
| Artifact Registry | Bounded metadata and references for plans, commits, PRs, CI, QA, and gate evidence |
| Human Authority | Exact G4/G5/G6 approval for a specific action and immutable scope |
| SLO | Operational objective for queueing, stale detection, recovery, and evidence freshness |
| Runtime SSOT | DS Admin/AgentOps |
| Spec SSOT | Repository specs and protected-base governance |

## Requirements

### Requirement 1: Versioned Declarative Workflows

**User Story:** As a platform owner, I want versioned workflow templates, so that projects can run predictable stages without hard-coded linear transitions.

#### Acceptance Criteria

1. THE system SHALL store versioned workflow templates.
2. A template SHALL define stages, required roles, inputs, outputs, transitions, retry policy, gate requirement, and evidence schema.
3. A workflow run SHALL remain bound to its template version.
4. Template updates SHALL NOT silently alter in-flight runs.
5. THE system SHALL support linear and bounded branch/join workflows.
6. Only validated templates SHALL be activatable.

### Requirement 2: Multi-Project Adapter Model

**User Story:** As a Tech PM, I want project adapters, so that one Hub can coordinate repositories with different tools and conventions.

#### Acceptance Criteria

1. EACH project SHALL have a validated profile and adapter.
2. An adapter SHALL declare repository identity, protected branches, spec format, package manager, commands, CI provider, evidence mappings, file boundaries, and sensitive exclusions.
3. Adapter rules SHALL tighten but SHALL NOT weaken GWC.
4. Missing or invalid adapters SHALL block repository execution.
5. Project adapters SHALL support Kiro, Codex, Claude, and other local runtimes through the same server contracts.

### Requirement 3: Role-Separated Agents

**User Story:** As a governance owner, I want distinct Lead, Dev, QA, Reviewer, Operator, and System roles, so that no agent self-authorizes an entire delivery lifecycle.

#### Acceptance Criteria

1. Roles SHALL have server-enforced capabilities.
2. Stage tasks SHALL declare exactly one required role.
3. Claim SHALL require role, capability, repository scope, and active lease.
4. Reviewer acceptance SHALL be separate from Dev and QA execution.
5. G4/G5/G6 SHALL remain exact human authority even when an executor agent performs the approved action.
6. Conflicting duties SHALL be blocked or explicitly disclosed according to policy.

### Requirement 4: Durable Claims, Leases, and Recovery

**User Story:** As an operator, I want durable ownership and recovery, so that distributed agents cannot duplicate or abandon work silently.

#### Acceptance Criteria

1. Claims SHALL be atomic, targeted, auditable, and lease-bound.
2. Active agents SHALL publish heartbeats.
3. Lease renewal and release SHALL verify owner identity.
4. Scheduler SHALL recover expired leases and stale agents.
5. Retry, backoff, dead-letter, and human-intervention behavior SHALL be policy-driven.
6. Duplicate result submissions SHALL be idempotent.

### Requirement 5: Evidence and Artifact Registry

**User Story:** As a Reviewer, I want all delivery evidence linked, so that I can reconstruct the exact decision and code state.

#### Acceptance Criteria

1. THE system SHALL register plan, gate, commit, PR, CI, QA, review, merge, deploy, and production-operation evidence as bounded metadata and references.
2. Evidence SHALL bind to repository, task, workflow, scope hash, and immutable SHA where applicable.
3. Stale or ambiguous evidence SHALL be rejected.
4. Large logs and binaries SHALL be referenced rather than stored unbounded.
5. Secrets SHALL be redacted.
6. Evidence retention and cleanup SHALL preserve valuable decisions and remove low-value transient noise according to policy.

### Requirement 6: State Engine Integrity

**User Story:** As a platform owner, I want all runtime transitions controlled by one State Engine, so that generic CRUD cannot corrupt workflow state.

#### Acceptance Criteria

1. Generic CRUD SHALL NOT mutate stage, current task, claim, lease, or gate state.
2. Every transition SHALL validate template, current state, actor role, evidence, and idempotency.
3. Illegal or ambiguous transitions SHALL fail closed.
4. Multi-record consistency-critical transitions SHALL be transactional.
5. Event history SHALL be append-only or equivalently auditable.
6. Repository projections SHALL not override runtime state.

### Requirement 7: Git and CI Integration

**User Story:** As a Delivery Lead, I want exact Git and CI binding, so that agents act only on the intended code revision.

#### Acceptance Criteria

1. Repository writes SHALL use guarded branches and expected-SHA checks.
2. Direct protected-branch write, force-push, history rewrite, branch deletion, and PR-base change SHALL be prohibited by default.
3. CI events SHALL match repository and immutable revision identity.
4. QA and review evidence SHALL match the current PR head SHA.
5. CI repair SHALL be bounded and root-cause aware.
6. Merge SHALL require exact G4 authority.

### Requirement 8: Quality Policy Profiles

**User Story:** As a QA Lead, I want project and risk-based quality policies, so that required tests match the change.

#### Acceptance Criteria

1. Quality policies SHALL select required checks by project, risk, modules, and change type.
2. Policies SHALL define unit, integration, UI, contract, security, performance, migration, and denial-case requirements where applicable.
3. Skipped checks SHALL require reason and reviewer visibility.
4. Coverage SHALL be used where meaningful but SHALL NOT be the sole quality signal.
5. QA Agent SHALL NOT alter production behavior merely to make tests pass.
6. High-risk changes SHALL require stricter and sequential review.

### Requirement 9: Observability and Operations

**User Story:** As an operator, I want a control-plane dashboard and alerts, so that stalled or unsafe workflows are visible.

#### Acceptance Criteria

1. Dashboard SHALL expose workflows, stages, owners, agents, queues, leases, CI, QA, blockers, retries, dead-letter, and human actions.
2. The system SHALL expose SLO metrics for queue wait, stale detection, lease recovery, evidence freshness, and workflow duration.
3. Alerts SHALL be actionable and link to workflow/task evidence.
4. Operator actions SHALL be role-controlled, idempotent, and auditable.
5. Scheduled maintenance SHALL clean expired transient records without deleting required audit history.

### Requirement 10: Security, Privacy, and Tenant Boundaries

**User Story:** As a security owner, I want consistent control-plane security, so that agents cannot cross project or production boundaries.

#### Acceptance Criteria

1. Auth, role, ownership, resource relationship, rate limits, request IDs, and secret redaction SHALL be server-side.
2. Repository allowlists and project identity SHALL be validated.
3. Agent credentials SHALL use least privilege and rotation policy.
4. Production data/config/credential operations SHALL require G6.
5. Cross-project data SHALL be isolated by project/workflow authorization.
6. Prompt or repository content SHALL NOT grant authority.

### Requirement 11: Human Decision Boundaries

**User Story:** As the accountable owner, I want exact human control over merge, deploy, and production operations, so that automation cannot exceed delegated authority.

#### Acceptance Criteria

1. G4 merge approval SHALL bind repository, task, PR, head SHA, scope hash, method, and expiry.
2. G5 deployment approval SHALL bind release/commit, environment, action, rollback, and expiry.
3. G6 approval SHALL bind the exact production operation and data/config scope.
4. Earlier gates, CI pass, QA pass, or tool capability SHALL NOT imply later authority.
5. Every authority SHALL expire and be auditable.

### Requirement 12: Migration and Compatibility

**User Story:** As a portfolio owner, I want gradual adoption, so that current projects are not forced into a risky big-bang migration.

#### Acceptance Criteria

1. Existing workflows SHALL remain supported during a versioned migration period.
2. Projects SHALL adopt runtime SSOT through an explicit adapter and tracking mode.
3. Repository task files MAY remain projections during migration.
4. Pilot, single-project, and multi-project rollout SHALL have separate go/no-go gates.
5. Rollback SHALL be possible by disabling a template or adapter without rewriting repository history.
