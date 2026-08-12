# Gate Authority Node Catalog (MAT-F2)

Final integration owner for the `gate_authority` node family.

## Nodes
| Node | Module | Public entry |
|------|--------|--------------|
| SCRUM-185 | tools/node_architect/approval_token_generation.py | generate_gate_approval_token |
| SCRUM-186 | tools/node_architect/approval_command_validation.py | validate_gate_approval_command |
| SCRUM-190 | tools/node_architect/gate_transition_decision.py | decide_gate_transition |
| SCRUM-191 | tools/node_architect/g2_execution_envelope_render.py | render_g2_execution_envelope |
| SCRUM-192 | tools/node_architect/blocked_action_escalation.py | escalate_blocked_action |
| SCRUM-312 | tools/node_architect/evidence_artifact_map.py | build_gate_evidence_artifact_map |

## Contract
- Each node is pure and offline; no execution authority is granted.
- Each node ships a closed JSON schema + focused M5 tests.
- Shared owner: `tools/node_architect/validate_node_catalog_gate_authority.py`.

## Run
```bash
PYTHONPATH=. python3 -m unittest tests.test_gate_authority_m5_family_flow
PYTHONPATH=. python3 -m unittest tests.test_node_catalog_gate_authority
```
