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
