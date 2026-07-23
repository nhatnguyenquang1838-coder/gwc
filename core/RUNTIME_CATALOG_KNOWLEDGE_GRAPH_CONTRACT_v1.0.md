# Runtime Catalog Knowledge Graph Contract v1.0

## Purpose

This contract standardizes the language and graph shape for the GWC runtime catalog so agents can distinguish gates, capability families, runtime nodes, edge scenarios, and artifacts without inventing parallel terminology.

## Canonical taxonomy

| Level | Canonical name | Meaning | Example |
|---|---|---|---|
| L0 | Gate | Authority boundary in the G0-G6 lifecycle. | `G5_DEPLOY` |
| L1 | Capability Family | A cohesive group of runtime capabilities. | `repo_delivery` |
| L2 | Runtime Node | One executable or observable behavior descriptor. | `repo-delivery-ci-run-capture` |
| L3 | Edge Scenario | A failure, exception, retry, or alternate route handled by nodes. | `missing_workflow_run` |
| L4 | Artifact | Source, schema, validator, test, checkpoint, evidence, package export, or generated KG file. | `schemas/node-architect/runtime-node.schema.json` |

The phrase `81 nodes` must mean **81 Runtime Nodes**, not gates, workflows, runbooks, or task items.

## Current catalog invariant

```text
9 Capability Families
× 9 Runtime Nodes each
= 81 Runtime Nodes
```

The current family set is:

```yaml
families:
  - intake_context
  - gate_authority
  - repo_delivery
  - runtime_checkpoint
  - validation_quality
  - sync_projection
  - package_export
  - failure_recovery
  - scale_control
```

Changing the family count, node count, or existing public node IDs requires a separate G1 decision and migration plan.

## Relationship model

Runtime catalog KG projections must use these canonical edge labels:

| Relationship | Source → Target | Meaning |
|---|---|---|
| `BELONGS_TO_FAMILY` | Runtime Node → Capability Family | Node is owned by a family. |
| `GOVERNED_BY_GATE` | Runtime Node or Scenario → Gate | Execution authority boundary. |
| `IMPLEMENTED_BY` | Runtime Node or Family → Artifact | Source/runbook/schema that defines it. |
| `VALIDATED_BY` | Runtime Node or Artifact → Validator/Test | Validation coverage. |
| `HANDLES_SCENARIO` | Runtime Node → Edge Scenario | Node covers the scenario. |
| `DEPENDS_ON_NODE` | Runtime Node → Runtime Node | Runtime ordering or evidence dependency. |
| `EXPORTED_BY_PACKAGE` | Artifact → Package | Artifact is exported to generated governance packages. |
| `ALIASED_BY` | Runtime Node or Family → Alias | Backward-compatible name mapping. |

## Node identity rules

A Runtime Node identity must remain stable once exported:

```yaml
id: repo-delivery-ci-run-capture
type: runtime_node
family: repo_delivery
canonical_name: CI Run Capture
aliases:
  - ci.run_capture
  - workflow_run_capture
```

Rules:

1. `id` is the stable registry key.
2. `type` must be one of `gate`, `capability_family`, `runtime_node`, `edge_scenario`, or `artifact`.
3. `family` is required for runtime nodes.
4. Aliases are compatibility only and must not become new nodes.
5. Generated KG artifacts must preserve source path and source SHA when available.

## Compatibility with generated KG artifacts

Knowledge graph outputs are derived artifacts. Do not hand-edit generated KG outputs when a canonical source or projection tool exists. Normalization must happen in source contracts, schemas, registries, and projection tools first, then generated KG artifacts may be refreshed through the approved generator path.

## G5 CI mapping

The G5 CI enhancement must be represented as a capability expansion across existing families:

```yaml
gate: G5_DEPLOY
primary_family: repo_delivery
supporting_families:
  - runtime_checkpoint
  - validation_quality
  - failure_recovery
  - sync_projection
node_count_change: 0
new_runtime_nodes: []
contract_artifacts:
  - core/G5_CI_VERIFICATION_CONTRACT_v1.0.md
  - schemas/g5-ci-verification-evidence.schema.json
  - schemas/node-architect/g5-ci-checkpoint.schema.json
```

It must not create a tenth family or an eighty-second runtime node unless a later approved scope explicitly changes the catalog cardinality.

## Forbidden terminology drift

```text
❌ 81 gates
❌ 81 workflows
❌ 81 runbooks
❌ G5 node family as a new family
❌ KG output as source of truth
```

Use:

```text
✅ GWC Runtime Capability Catalog
✅ 9 Capability Families
✅ 81 Runtime Nodes
✅ Edge Scenarios
✅ Artifact Graph
```
