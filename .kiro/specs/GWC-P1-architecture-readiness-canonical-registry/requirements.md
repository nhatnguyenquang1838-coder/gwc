# Requirements — GWC Phase 1 Architecture Readiness & Registry Foundation

## 1. Purpose

This spec defines the Phase 1 implementation baseline for SCRUM-95: Architecture Readiness & Canonical Registry Foundation.

The work prepares GWC for future durable runtime, compiler, scenario engine and DW SUPER APP integration. It is intentionally planning and architecture focused. It does not implement runtime behavior or grant merge/deploy/production authority.

## 2. Scope

### In scope

- Audit current GWC contracts, blockers and executable surfaces.
- Define DW SUPER APP source-of-truth and authority boundaries.
- Design canonical runtime schemas for nodes, scenarios, profiles, decisions and history.
- Resolve readiness blockers around lifecycle, authority validation, workspace and package integrity.
- Build registry/validator/v3-binding implementation plan.
- Preserve Task-Me provenance and per-subtask evidence.

### Out of scope

- Implementing the Phase 2 runtime engine.
- Creating or merging production PRs.
- Deploying or releasing packages.
- Changing protected branch policy.
- Performing G5/G6 operations.

## 3. Functional requirements

### FR-1 Current-state baseline

The system shall produce a source-backed baseline for current GWC state.

Acceptance criteria:

- AC-1.1: Baseline lists all relevant governance contracts, schemas, validators, skills and profiles.
- AC-1.2: Baseline classifies each surface as implemented, partial, contract-only, proposed or obsolete.
- AC-1.3: Baseline identifies readiness blockers with severity and evidence.

### FR-2 Source-of-truth matrix

The system shall define a source-of-truth matrix for GWC + DW SUPER APP + UA + Task-Me + BMAD.

Acceptance criteria:

- AC-2.1: The matrix separates governance authority, planning, knowledge, procedure execution and projection.
- AC-2.2: Jira/task board state is explicitly non-authoritative.
- AC-2.3: Human authority is retained for merge, deploy, production and stable catalog promotion.

### FR-3 Canonical runtime schema design

The system shall design schemas for the canonical runtime model.

Acceptance criteria:

- AC-3.1: Schemas cover node contract, scenario contract, decision rule, runtime graph, graph revision and routing history.
- AC-3.2: Node metadata separates effect, authority, reversibility, idempotency, suspension and determinism.
- AC-3.3: Schema design distinguishes runtime edges from visualization edges.

### FR-4 Readiness blocker resolution plan

The system shall produce an implementation plan to resolve audited blockers.

Acceptance criteria:

- AC-4.1: The plan covers G4/G5 lifecycle mismatch.
- AC-4.2: The plan covers connector action authority validation.
- AC-4.3: The plan covers task workspace canonicalization.
- AC-4.4: The plan covers G3 ready-for-review contradictions.
- AC-4.5: The plan covers package/integrity drift.

### FR-5 Registry and v3 visual binding plan

The system shall define how the v3 visual scenario graph will bind to canonical registry data.

Acceptance criteria:

- AC-5.1: v3 reads registry-backed node/scenario/flow data instead of hard-coded scenarios.
- AC-5.2: Visualization-only edges cannot drive runtime execution.
- AC-5.3: Registry promotion requires validation and review.

## 4. Non-functional requirements

- NFR-1: All artifacts must bind to repository `nhatnguyenquang1838-coder/gwc` and protected base SHA.
- NFR-2: Planning artifacts must be replayable and traceable to Task-Me run output.
- NFR-3: Any future write must be bounded by G2 scope hash.
- NFR-4: No generated artifact may imply G4, G5 or G6 authority.

## 5. Traceability

This spec maps to Jira parent SCRUM-95 and subtasks SCRUM-100 through SCRUM-104.

## 6. Restart note

This R2 package supersedes the stale first execution package. The previous branch remains audit-only and must not be used for PR delivery.
