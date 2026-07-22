# package_export node family

Task: `SCRUM-68`  
Batch: `batch-07-package-export`  
Family: `package_export`  
Planned nodes: 9  
Authority boundary: `G2_EXECUTION_G3_PR`

This family models deterministic GWC consumer-package build, export, manifest, readback, and smoke-verification behavior. It extends the existing `CONSUMER_PACKAGE_EXPORT_RULE`, exporter, manifest schema, and smoke test; it does not create a new publisher or consumer-repository mutation path.

## Scope

Allowed:

- add exactly 9 `package_export` node descriptors;
- add one family README;
- add a stdlib validator and focused unit tests;
- export the new family through `projects/gwc/package.yaml`;
- add one changelog fragment.

Forbidden:

- rewriting `tools/export_project_package.py`;
- changing `package_version`;
- publishing packages or updating consumer repositories;
- implementing Batch 08 `failure_recovery` or Batch 09 `scale_control`;
- merge, auto-merge, deploy, release, production configuration/data, credentials, secrets, or migration operations.

## Nodes

| Node | Type | Purpose |
|---|---|---|
| `package-export-package-manifest-load` | tool | Load bounded package entries in stable order. |
| `package-export-entry-schema-validation` | gate | Validate closed entry shape before export. |
| `package-export-source-path-safety-check` | gate | Block unsafe or missing required sources. |
| `package-export-target-path-safety-check` | gate | Block unsafe, duplicate, or escaping targets. |
| `package-export-governance-tree-build` | workflow | Build the generated `.governance/` tree. |
| `package-export-export-manifest-generation` | workflow | Record deterministic package evidence. |
| `package-export-deterministic-hash-verification` | gate | Verify copied bytes and manifest hashes. |
| `package-export-smoke-verification` | workflow | Exercise the real package export contract. |
| `package-export-export-failure-routing` | workflow | Route bounded export failures without publishing. |

## Guardrails

```text
✅ exactly 9 nodes
✅ canonical=delivery_evidence
✅ authority_boundary=g2_required
✅ gates limited to G2_EXECUTION and G3_PR
✅ reuse existing exporter and smoke verifier
✅ deterministic SHA-256 readback
❌ no package version change
❌ no package publish or consumer mutation
❌ no G4/G5/G6 authority
```
