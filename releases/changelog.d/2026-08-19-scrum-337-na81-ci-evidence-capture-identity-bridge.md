feat(gwc): SCRUM-337 NA81 ci-evidence-capture descriptor/route identity bridge

Implement the SCRUM-337 (NA81-R10) bounded S2 delta that wires the existing
`validation_quality.ci-evidence-capture` node (runtime id dotted form) to its
kebab-case catalog descriptor `validation-quality-ci-evidence-capture` through the
controller-specified `registry_provenance_source_path_identity_bridge`, without
mutating the descriptor, registry identity, or node-instruction schema.

New behavior (backward-compatible — all 10 existing routes resolve unchanged):

- `tools/node_architect/validate_node_instruction.py` resolves the descriptor
  identity through the registry entry whose `provenance.source_path` matches the
  route descriptor path, then enforces
  `card.node_id == resolved registry runtime id == route.current_node`.
- The bridge fails closed on missing, ambiguous, or mismatched provenance
  (NODE_INSTRUCTION_INVALID) so a wrong descriptor can never silently bind to the
  wrong runtime node.
- `tools/node_architect/resolve_gate_node_route.py` MATURITY scale gains the
  `candidate` level (between experimental and pilot). This was a pre-existing
  scale gap: two existing routes (`repo_delivery.ci-run-capture`,
  `validation_quality.ci-evidence-capture`) bind `candidate` nodes that the
  scale previously mapped to -1 and wrongly blocked. Adding `candidate` unblocks
  them and makes the SCRUM-337 route selectable. No existing route behavior
  changed (all prior nodes are experimental/pilot/stable).

New files:
- core/node-architect/node-instructions/validation_quality/ci-evidence-capture.node-instruction.yaml (node-instruction card, validates in all 5 modes)
- core/node-architect/node-instructions/validation_quality/ci-evidence-capture.node.instruction-card.json (instruction-card artifact, validates against instruction-card.schema.json)
- tests/test_na81_validate_node_instruction_identity_bridge.py (4 fail-closed regression tests: positive + mismatch/ambiguous/missing provenance)
- tests/test_validation_quality_ci_evidence_capture_instruction.py (16 instruction + route-binding tests, scoped to the bounded S2 delta)
- releases/changelog.d/2026-08-19-scrum-337-na81-ci-evidence-capture-identity-bridge.md

Updated files:
- core/node-architect/gate-node-route-profile.json (added route g3-ci-evidence-capture: gate G3_PR, current_node validation_quality.ci-evidence-capture, node_descriptor_ref validation-quality-ci-evidence-capture.node.json, node_instruction_ref ci-evidence-capture.node-instruction.yaml, requested_action ci_evidence_capture, implementation tools/node_architect/ci_evidence_capture.py:capture_ci_evidence)
- tools/node_architect/validate_node_instruction.py (registry_provenance_source_path_identity_bridge)
- tools/node_architect/resolve_gate_node_route.py (MATURITY scale: candidate level)

All authority fields are fixed to false; the node grants no G2/G3/G4/G5/G6
authority. CI evidence capture is observability only; merge/promotion to pre-prod
or main remains Human-G4. No connector call, network request, filesystem mutation
outside the bounded S2 scope, Jira transition, approval, merge, deployment,
release, or production operation.

Related: SCRUM-337 (#272), Epic SCRUM-288, NA81-R10
(AR-SCRUM288-RECERT-20260814-R10). Predecessor SCRUM-294 family; consumer of the
existing capture_ci_evidence implementation.
