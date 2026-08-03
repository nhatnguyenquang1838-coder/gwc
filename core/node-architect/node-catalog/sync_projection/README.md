# sync_projection node family

Task: `REVAMP-GWC-022`  
Batch: `batch-06-sync-projection`  
Family: `sync_projection`  
Planned nodes: 9  
Authority boundary: `read_only`; applicability gates: `G2_EXECUTION_G3_PR`

This family defines controlled audit-projection nodes for DS Admin, Task Center, and external audit surfaces. Canonical repository, gate, PR, CI, and task evidence remains authoritative; projected state is never approval or execution authority.

## Scope

Allowed:

- add exactly 9 `sync_projection` node descriptors;
- add one family README;
- add a stdlib validator and focused unit tests;
- add package export entries;
- add a changelog fragment.

Forbidden:

- implementing DS Admin, Task Center, or connector runtimes;
- making projected state canonical;
- projecting secrets, credentials, production configuration, production data, or hidden reasoning;
- implementing the full 81-node catalog;
- runtime engine, scheduler, or worker implementation;
- merge, auto-merge, deploy, or release changes;
- package version changes.

## Nodes

| Node | Type | Applicability gates |
|---|---|---|
| `sync-projection-ds-admin-state-projection` | projection | G2, G3 |
| `sync-projection-task-center-sync` | connector | G2, G3 |
| `sync-projection-external-audit-event-projection` | projection | G2, G3 |
| `sync-projection-projection-source-authority-check` | gate | G2 |
| `sync-projection-projection-drift-detection` | workflow | G2, G3 |
| `sync-projection-projection-reconcile-readback` | workflow | G2, G3 |
| `sync-projection-projection-failure-routing` | workflow | G2, G3 |
| `sync-projection-projection-evidence-linking` | projection | G2, G3 |
| `sync-projection-projection-privacy-boundary-check` | gate | G2, G3 |

## Guardrails

```text
✅ exactly 9 nodes
✅ canonical=audit_projection
✅ authority_boundary=read_only
✅ gates are applicability metadata limited to G2_EXECUTION and G3_PR
✅ source authority, drift detection, readback, failure routing, evidence linking, and privacy boundary are explicit
✅ external projection is audit evidence only
❌ no G2/G3/G4/G5/G6 authority grant from projection state
❌ no runtime or connector implementation
❌ no package version change
```

## M4 runtime contracts

Runtime contracts extend the thin descriptors without turning projection state into authority. The evaluator layer is pure: it performs no connector call, network request, filesystem mutation, Jira transition, branch/PR action, approval, merge, deployment, release, or production operation.

| Descriptor | Runtime artifact | Schema | Evaluator | Maturity |
|---|---|---|---|---|
| `projection-source-authority-check.node.json` | `projection-source-authority-decision` | `schemas/projection-source-authority-decision.schema.json` | `tools/node_architect/projection_source_authority_check.py` | M4 deterministic |

### Projection source authority decision

`decide_projection_source_authority(...)` fails closed unless every requested projected field is bound to exact, current, canonical evidence. It rejects:

- missing canonical sources;
- projection/advisory-only authority;
- unbound or inferred fields;
- ambiguous or conflicting bindings;
- revision or digest mismatch;
- stale source or readback evidence;
- unknown deterministic derivation rules.

The output is a closed `schema_version: "1.0"` artifact with deterministic ordering and a `sha256:` decision digest. Output `observed_at` and `decision_digest` are excluded from digest input; evidence timestamps remain semantic. Every authority grant remains fixed to `false`, while `read_only_projection` remains fixed to `true`.
