# Design Document

## Overview

Phase 1 introduces a canonical planning and registry foundation around the existing GWC governance system. The design extends current contracts rather than replacing them and keeps Task-Me as a planning-only component.

## Architecture

```text
Protected-base GWC evidence
        鈹?        鈻?Standalone Task-Me scan
        鈹?        鈹溾攢鈹€ per-task planning package
        鈹溾攢鈹€ planning/traceability graph
        鈹斺攢鈹€ Kiro requirements/design/tasks projection
        鈹?        鈻?GWC G0/G1 validation
        鈹?        鈻?Bounded G2 implementation tasks
        鈹?        鈻?Registry validation + Cytoscape v3 binding
```

Three knowledge lanes run in parallel:

```text
Current-state audit 鈹€鈹€鈹€鈹€鈹€鈹?Authority matrix 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹尖啋 Blocker resolution 鈫?Registries + v3 binding
Schema design 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?```

## Components and Interfaces

### TaskMeConsumerConfig

Suggested path:

```text
.task-architect/config.json
```

Responsibility:

- Define GWC repository source globs.
- Keep outputs inside `.task-me/runs`.
- Keep Task-Me output-only.
- Allow discovery tasks when exact symbols require checkout verification.

### TaskMeRunPackage

Suggested path:

```text
.task-me/runs/<run-id>/
```

Responsibility:

- Store shared source inventory, traceability, evidence graph and validation report.
- Store exactly one self-contained folder per task.
- Produce task index and dependency DAG.

### CanonicalRegistrySchemas

Suggested paths:

```text
schemas/runtime/node-contract.schema.json
schemas/runtime/scenario-contract.schema.json
schemas/runtime/flow-profile.schema.json
schemas/runtime/decision-rule.schema.json
schemas/runtime/runtime-graph.schema.json
schemas/runtime/routing-history.schema.json
```

Responsibility:

- Validate stable IDs, versioning, contracts and provenance.
- Separate runtime and visualization relationships.
- Prevent implicit promotion.

### RegistryValidator

Suggested path:

```text
tools/validate_runtime_registry.py
```

Interface:

```python
def validate_registry(root: Path) -> ValidationReport:
    ...
```

Responsibility:

- Validate schemas and cross-references.
- Enforce 81-slot family invariant where applicable.
- Reject unresolved runtime edges and invalid scenario targets.

### V3RegistryAdapter

Suggested path:

```text
tools/node_architect/viewer/
```

Interface:

```ts
type RegistryBundle = {
  nodes: RuntimeNodeDefinition[]
  scenarios: ScenarioDefinition[]
  flows: FlowProfile[]
}
```

Responsibility:

- Load registry data.
- Render full graph.
- Apply active/dim classes without deleting inactive nodes.
- Display path/history/authority metadata.

## Data Models

### RuntimeNodeDefinition

```ts
type RuntimeNodeDefinition = {
  id: string
  version: string
  family: string
  maturity: "experimental" | "candidate" | "pilot" | "stable" | "deprecated" | "retired"
  sourceStatus: "canonical_explicit" | "proposed_registry_slot"
  effectClass: "read_only" | "local_write" | "external_write" | "destructive"
  authorityClass: "automatic" | "delegated" | "human_required" | "prohibited"
  reversibility: "reversible" | "compensatable" | "irreversible" | "unknown"
  idempotency: "intrinsic" | "key_required" | "readback_required" | "non_idempotent"
  evidenceContract: string
  implementationRefs: string[]
}
```

### ScenarioDefinition

```ts
type ScenarioDefinition = {
  id: string
  version: string
  activation: unknown
  factsSchema: string
  rules: TypedGuard[]
  nodes: string[]
  edges: ScenarioEdge[]
  greenTargets: string[]
  humanBoundaries: string[]
}
```

### RoutingHistory

```ts
type RoutingHistory = {
  runId: string
  graphRevision: number
  observedFacts: Record<string, unknown>
  candidateRoutes: RouteEvaluation[]
  selectedRoute?: string
  evidenceRefs: string[]
}
```

## Correctness Properties

### Authority Preservation

A runtime node or procedure result must never grant its own authority.

### Exact Binding

Evidence or approval bound to a different task, repository, SHA, scope or graph revision must not validate.

### Maturity Preservation

A proposed registry slot must never be rendered or executed as stable without promotion evidence.

### Scenario/Edge Distinction

The declared count of scenarios must not be inferred from the count of graph edges.

### Full-Graph Visualization

Inactive nodes remain visible and are dimmed; filtering must not silently change graph semantics.

## Error Handling

- Missing source evidence produces a discovery task or blocked registry entry.
- Invalid cross-reference fails registry validation.
- Unknown guard facts produce `CONDITIONAL`, not `VALID_AUTO`.
- Human-required routes stop at a decision packet.
- Connector timeout after a write requires readback and must not blind retry.

## Testing Strategy

- Schema meta-validation and positive/negative fixtures.
- Lifecycle and action-authority negative tests.
- Workspace compatibility tests.
- Registry cross-reference tests.
- V3 fixture tests for dimming and route classes.
- Full repository validation and package build.
- Exact-head G3 review and CI evidence before readiness.

## Implementation Constraints

- Reuse and extend existing validators and contracts.
- Do not modify protected `main` directly.
- Do not weaken G0-G6 authority.
- Do not implement the durable runtime or graph compiler in this phase.
- Do not represent planning-only Task-Me output as runtime evidence.
- Do not include merge, deployment, release, credentials or production data.

