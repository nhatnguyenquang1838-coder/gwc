# Requirements Document

## Introduction

SCRUM-115 completes the P3 integration lane by materializing an initial canonical scenario set, binding those scenarios to deterministic typed routing, and exposing runtime and immutable history state through the registry-backed Cytoscape v3 adapter. SCRUM-113 and SCRUM-114 are merged prerequisites. This specification is task-specific and replaces the stale K1/K2-only plan reference for G2 execution.

## Glossary

- **Canonical scenario**: A versioned source-backed runtime scenario with stable ID, activation facts, typed guards, route nodes, evidence references, and provenance.
- **Green target**: A safe governed outcome that a route may terminate at.
- **Authority boundary**: A gate or human decision point that stops automatic execution.
- **Routing history**: Immutable, graph-revision-bound records of scenario activation, evaluated guards, candidate routes, classification, ranking, and selected outcome.
- **Projection edge**: A non-executable Cytoscape edge used only for visualization or history linkage.

## Requirements

### Requirement 1: Initial canonical scenario coverage

**User Story:** As a GWC runtime operator, I want a representative canonical scenario set, so that common delivery failures and ambiguity states are routed consistently.

#### Acceptance Criteria

1. WHEN SCRUM-115 is delivered THEN the scenario registry SHALL materialize exactly 14 initial canonical scenarios.
2. THE set SHALL cover missing context, ambiguity, baseline drift, scope drift, ambiguous write outcome, CI pending, CI failure, CI SHA mismatch, stale review, approval expiry, observability gap, partial deployment, production partial success, and blocked authority.
3. EACH scenario SHALL have a stable kebab-case ID and semantic version.

### Requirement 2: Contract and provenance integrity

**User Story:** As a governance validator, I want every scenario to be schema-valid and source-backed, so that registry entries cannot silently drift.

#### Acceptance Criteria

1. EACH scenario SHALL include activation facts, typed guard definitions, route nodes, edges, green targets, human boundaries, evidence references, and provenance.
2. THE registry SHALL distinguish declared scenario space from materialized scenarios.
3. THE validator SHALL reject duplicate IDs, unresolved rule or node references, mismatched materialized counts, invalid provenance, and executable visual-only edges.

### Requirement 3: Deterministic routing integration

**User Story:** As an execution engine, I want scenarios evaluated through the P3 typed guard and all-path router, so that route decisions are deterministic and safe.

#### Acceptance Criteria

1. SCENARIO activation SHALL use strict typed comparison without implicit truthiness coercion.
2. CANDIDATE routes SHALL be classified as `VALID_AUTO`, `VALID_HUMAN`, `CONDITIONAL`, `BLOCKED`, or `UNSAFE`.
3. HUMAN, blocked, conditional, and unsafe routes SHALL NOT auto-execute.
4. ROUTE ordering SHALL be deterministic for identical graph revision, scenario, and facts.

### Requirement 4: Immutable routing history

**User Story:** As an auditor, I want durable route-decision history bound to graph revision, so that execution decisions can be replayed and verified.

#### Acceptance Criteria

1. EACH decision record SHALL include scenario ID/version, graph revision, normalized facts digest, evaluated guard results, candidate routes, selected route, classification, and decision digest.
2. DECISION history SHALL be append-only in behavior and SHALL reject mutation of an existing decision ID with different content.
3. REPEATING the same decision input SHALL yield the same decision digest.

### Requirement 5: Registry-backed Cytoscape v3 projection

**User Story:** As a reviewer, I want the selected scenario and route history visible in Cytoscape v3, so that I can inspect why a route was selected without granting runtime authority.

#### Acceptance Criteria

1. THE adapter SHALL render scenario metadata, candidate-route status, selected-route status, and history bindings from registry and decision data.
2. HISTORY and visualization edges SHALL always set `runtime_executable` to false.
3. ACTIVE and inactive runtime nodes SHALL retain their existing registry-backed classes and provenance.

### Requirement 6: Compatibility and validation

**User Story:** As a maintainer, I want focused and regression validation, so that SCRUM-115 does not weaken existing P3 or registry guarantees.

#### Acceptance Criteria

1. EXISTING SCRUM-113/114 compiler and routing tests SHALL continue to pass.
2. THE canonical runtime registry validator SHALL pass with 81 nodes and 14 materialized scenarios while preserving 116 declared scenarios.
3. FOCUSED tests SHALL cover all 14 IDs, schema validation, deterministic decision digest, authority stops, blocked/conditional behavior, immutable history, and non-executable projection edges.
4. THE implementation SHALL stay within the approved SCRUM-115 file scope and SHALL NOT grant merge, deploy, release, production, credential, migration, force-push, branch-delete, or PR-base-change authority.
