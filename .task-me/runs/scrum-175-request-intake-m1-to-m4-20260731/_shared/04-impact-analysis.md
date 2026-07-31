# Impact Analysis

## Overview

SCRUM-175 is a bounded G0 context change inside the existing `intake_context` node family. The current node descriptor is already present, and the family already has a validator plus regression tests. The task therefore extends an established catalog surface rather than introducing a new family or authority boundary.

## Direct Impact

- `core/node-architect/node-catalog/intake_context/request-intake.node.json`
  - This is the primary contract surface.
  - It currently describes a `workflow` node with `canonical: canonical`, `authority_boundary: read_only`, and `gates: ["G0_CONTEXT"]`.
  - The task will add machine-readable intake fields without changing the G0-only boundary.
- `tools/node_architect/validate_node_catalog_intake_context.py`
  - The validator currently enforces exactly nine nodes, read-only/none authority, and a single `G0_CONTEXT` gate.
  - It must be extended to understand the richer request-intake contract and continue failing closed on drift.
- `tests/test_node_catalog_intake_context.py`
  - Current tests cover count, gate, and authority rejection.
  - The new tests must cover deterministic normalization, malformed input, ambiguity rejection, and stable reason-code behavior.

## Transitive Impact

- `core/node-architect/node-catalog/intake_context/README.md`
  - The family README already names `request-intake` as the node that normalizes user requests into bounded intake facts.
  - If the node grows typed input/output details, the README should stay aligned.
- `core/node-architect/runtime-graph-registry.json`
  - The runtime graph lists `intake_context.request-intake` as a canonical runtime node.
  - Any contract expansion should preserve the registry identity and the existing family topology.
- `core/node-architect/node-registry.json`
  - The registry is the authoritative catalog of runtime nodes.
  - Changes to the node descriptor should keep registry provenance and slot review coherent.
- `core/KIRO_SPEC_DRIVEN_DELIVERY_RULE_v1.0.md`
  - This governs how Kiro specs are used in the repo.
  - The task plan should remain compatible with the repo-local planning rules.
- `core/runbooks/GATE_G0_G1_OPERATIONAL_RUNBOOK_v1.0.md`
  - This constrains gate-adjacent planning and evidence capture.
  - The request-intake change must not imply broader authority than G0 context.

## Exclusions

- No production runtime behavior beyond the node catalog and its validator/test harness.
- No deployment, merge, migration, credential, or production-data work.
- No new external connectors or task-system writes.

## Risk Notes

- The main risk is introducing extra node fields that the existing validator rejects by default.
- A second risk is overfitting the contract to one request shape and losing deterministic normalization.
- A third risk is drifting from the current G0-only boundary and accidentally expanding authority.

## Recommendation

Keep the implementation focused on the existing catalog node, validator, and tests. If the typed intake contract needs a helper or schema artifact, discover that target first and bind it to the current family rather than creating a parallel entrypoint.
