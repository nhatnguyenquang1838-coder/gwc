# SCRUM-192 — Design

## Schema
`blocked-action-escalation.schema.json`: closed object, `artifact_type: blocked-action-escalation`,
`decision` enum (ESCALATE / WAIT / RESOLVE_MINIMAL), `checkpoint_required`, `execution_performed: false`.

## Evaluator
`blocked_action_escalation.py`: pure function; computes `decision_digest` (sha256 over canonical inputs);
no side effects.

## Integration owner
`validate_node_catalog_gate_authority.py`: final shared owner validating the MAT-F2 gate_authority
node catalog (185/186/190/191/192) end-to-end.

## Tests
- `test_gate_authority_blocked_action_escalation_m5.py`: focused M5.
- `test_gate_authority_m5_family_flow.py`: integration across the family.
- `test_node_catalog_gate_authority.py`: catalog owner.
