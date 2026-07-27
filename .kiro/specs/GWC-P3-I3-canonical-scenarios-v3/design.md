# Design Document

## Overview

SCRUM-115 extends the existing P3 implementation rather than creating a second routing engine. Canonical scenario data remains in `core/node-architect/scenario-registry.json`; schema contracts remain under `schemas/runtime`; deterministic typed guard and route evaluation remain in `tools/p3_backward_graph.py`; cross-registry checks remain in `tools/node_architect/validate_runtime_registry.py`; Cytoscape projection remains in `tools/node_architect/viewer/registry_adapter.py`.

## Architecture

```text
canonical scenario registry
        │
        ├── schema + cross-reference validation
        │
        ├── activation + typed guard evaluation
        │       └── all-simple-path classification and ranking
        │
        ├── immutable route-decision record
        │       └── graph revision + normalized facts digest
        │
        └── Cytoscape v3 projection
                ├── runtime registry elements
                ├── scenario/route decision elements
                └── non-executable history edges
```

The existing node, graph, profile, and decision-rule registries remain authoritative. Scenario records reference those stable IDs; they do not create implicit runtime nodes or executable visual edges.

## Components and Interfaces

### Scenario registry

`core/node-architect/scenario-registry.json` stores 14 materialized scenarios while retaining `declared_scenario_count: 116`. Each scenario adds a `guards` array and a `route_policy` object. Existing fields remain compatible.

### Scenario contract schema

`schemas/runtime/scenario-contract.schema.json` validates typed guards and route policy. Guard types align with the existing evaluator: `exists`, `equals`, `in`, `gte`, and `lte`.

### Routing engine

`tools/p3_backward_graph.py` adds a scenario-level decision function that:

1. validates activation facts;
2. evaluates guards strictly;
3. enumerates candidate routes using the existing deterministic router;
4. selects the highest-ranked safe eligible route;
5. emits a canonical decision record and SHA-256 digest;
6. optionally appends the record to an in-memory history list with immutability checks.

### Runtime registry validator

`tools/node_architect/validate_runtime_registry.py` validates:

- exact materialized count;
- unique scenario IDs;
- guard IDs and supported types;
- route policy references;
- scenario rule/node/edge resolution;
- non-executable visualization/history edges;
- provenance source hash where available.

### Cytoscape v3 adapter

`tools/node_architect/viewer/registry_adapter.py` accepts an optional `scenario_decision`. It overlays scenario, candidate route, selected route, and decision-history elements. All overlay edges are projection-only.

## Data Models

### Typed guard

```json
{
  "id": "ci-status-failed",
  "type": "equals",
  "field": "ci_status",
  "value": "failure",
  "conditional": false,
  "reason": "CI_FAILED"
}
```

### Route policy

```json
{
  "start_node": "repo_delivery.ci-run-capture",
  "green_targets": ["failure_recovery.timeout-recovery"],
  "allowed_authorities": [],
  "max_depth": 32
}
```

### Decision record

```json
{
  "decision_id": "sha256:<digest>",
  "scenario_id": "ci-failure",
  "scenario_version": "1.0.0",
  "graph_revision": "sha256:<digest>",
  "facts_digest": "sha256:<digest>",
  "guard_results": [],
  "candidate_routes": [],
  "selected_route": null,
  "classification": "BLOCKED"
}
```

## Correctness Properties

1. **Determinism:** identical registry, graph revision, scenario, and facts produce identical ordering and decision digest.
2. **Type safety:** booleans never equal integers and no guard uses implicit truthiness.
3. **Authority safety:** routes crossing unapproved authority boundaries never classify as `VALID_AUTO`.
4. **Projection safety:** scenario/history visualization edges are always non-executable.
5. **Immutability:** an existing decision ID cannot be rebound to different content.
6. **Registry integrity:** all rule, node, edge, green-target, and profile references resolve.

## Error Handling

- Missing activation facts produce a `CONDITIONAL` decision with explicit reasons.
- Unknown guard type produces a blocked guard result.
- Missing scenario, node, or green target raises a bounded validation/compile error.
- No eligible route produces `BLOCKED` or `UNSAFE`; it never falls through to auto-execution.
- Duplicate decision ID with changed content raises an immutability error.

## Testing Strategy

- Extend P3 unit tests for scenario activation, deterministic digests, authority stops, and immutable history.
- Add `tests/test_p3_scenario_registry.py` to verify all 14 scenarios and category coverage.
- Extend runtime registry validation tests from 3 to 14 materialized scenarios.
- Extend v3 adapter tests for selected/candidate route classes and non-executable overlay edges.
- Run full governance unit tests, compileall, diff scope checks, integrity checks, and exact-head GitHub Actions.

## Implementation Constraints

- Reuse existing P3 and registry mechanisms.
- Preserve 81-node and 116-declared-scenario invariants.
- No modification outside approved SCRUM-115 modules.
- No merge, deploy, release, production, credentials, migration, destructive operation, force-push, branch deletion, or PR base change.
