# Requirements Document

## Introduction

GWC requires an architecture-readiness baseline before expanding into a durable adaptive runtime. The current repository contains authoritative G0-G6 governance contracts, task-scoped evidence, exact-SHA verification and a declared runtime-catalog shape, but executable coverage and canonical registries remain incomplete.

This spec establishes the Phase 1 readiness and canonical-registry foundation. It is planning and contract work only. It does not implement the durable runtime, graph compiler, self-improvement, merge, deployment or production operations.

## Glossary

| Term | Definition |
|---|---|
| GWC | Governance control plane and canonical workflow authority. |
| Runtime Node | Governed capability executed inside an authorized runtime graph. |
| Edge Scenario | Runtime situation that activates decision/recovery routing; not equivalent to a graph edge. |
| Canonical | Source-backed, versioned and approved for stable use. |
| Proposed Registry Slot | Candidate catalog definition without complete production contract or promotion evidence. |
| Green Anchor | Critical state that a recovery route may safely return to. |
| V3 | Cytoscape full-flow scenario visualization baseline. |

## Requirements

### Requirement 1: Source-Backed Current-State Audit

**User Story:** As a GWC maintainer, I want every current capability and blocker classified using protected-base evidence, so that architecture decisions do not confuse contracts with executable runtime behavior.

#### Acceptance Criteria

1. WHEN the audit is produced THEN the system SHALL classify findings as implemented, partially implemented, contract-only, proposed, stale, or unknown.
2. WHEN a capability is called canonical THEN the report SHALL cite a verified repository path and implementation or contract evidence.
3. WHEN the 81-node catalog is reported THEN the system SHALL distinguish four explicit runtime-node IDs from proposed registry slots.
4. WHEN scenario counts are reported THEN the system SHALL NOT equate edge-scenario count with graph-edge count.

### Requirement 2: Explicit Authority and Source-of-Truth Matrix

**User Story:** As a DW SUPER APP architect, I want GWC, UA, Task-Me, BMAD, GitHub, deployment systems and Jira to have non-overlapping ownership, so that no component can silently assume authority.

#### Acceptance Criteria

1. WHEN canonical workflow state changes THEN GWC SHALL be the authority.
2. WHEN knowledge or impact context is generated THEN UA SHALL own the versioned knowledge output and SHALL NOT mutate workflow state.
3. WHEN implementation planning is generated THEN Task-Me SHALL own the plan and SHALL NOT execute repository or Jira mutations.
4. WHEN a BMAD procedure runs THEN its result SHALL be evidence/recommendation only.
5. Jira SHALL remain a projection and SHALL NOT grant G2-G6 authority.

### Requirement 3: Typed Canonical Registry Contracts

**User Story:** As a runtime implementer, I want typed versioned node, scenario, profile, graph and history contracts, so that execution and visualization use the same validated semantics.

#### Acceptance Criteria

1. Node contracts SHALL separate effect, authority, reversibility, idempotency, suspension and determinism metadata.
2. Scenario contracts SHALL define activation facts, typed guards, route nodes, green targets, evidence and human boundaries.
3. Runtime edges SHALL be distinct from visual grouping and suggested-sequence edges.
4. Free-form LLM text SHALL NOT be executable policy or a guard expression.
5. Stable IDs SHALL be versioned through a separate version field.

### Requirement 4: Readiness Blocker Resolution

**User Story:** As a GWC maintainer, I want lifecycle, authority validation, workspace, G3 readiness and package drift corrected, so that later runtime work builds on enforceable contracts.

#### Acceptance Criteria

1. G4/G5 behavior SHALL be consistent between contracts, transition state and tests.
2. Write-capable connector actions SHALL be checked against exact task, repository, SHA, scope and active authority.
3. New task artifacts SHALL use `.gwc/tasks/<task-id>/`.
4. PR head changes SHALL invalidate stale review and CI readiness evidence.
5. Package manifests, checksums and release metadata SHALL be reproducible by an inspected command.

### Requirement 5: Registry-Driven V3 Visualization

**User Story:** As an architecture reviewer, I want v3 to load external node, scenario and flow registries, so that the visualization reflects governed data instead of hard-coded examples.

#### Acceptance Criteria

1. V3 SHALL retain all nodes on the canvas and dim inactive nodes.
2. V3 SHALL distinguish happy path, history, valid routes, conditional routes, blocked routes and human-authority routes.
3. V3 SHALL enumerate all bounded simple routes to green rather than selecting only a shortest path.
4. Visual-only edges SHALL NOT be treated as runtime dependencies.
5. Every displayed node SHALL expose maturity and provenance.
