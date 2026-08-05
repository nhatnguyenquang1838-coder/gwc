# SCRUM-185 Requirements

Implement deterministic generation of an exact human approval request and command for one separately gated action. Generation creates a request for authority; it does not create authority.

## Create files
- `schemas/gate-approval-request.schema.json`
- `tools/node_architect/approval_token_generation.py`
- `tests/test_gate_authority_approval_token_generation_m4.py`

## Acceptance criteria
- Closed schema, exact command grammar `APPROVE <GATE_SHORT> <TASK_ID> <APPROVAL_TOKEN_64HEX> <EXPIRES_AT_UTC>`.
- Non-secret token semantics; possession alone does not authorize an action.
- Expiry/scope/head binding and drift sensitivity are tested.
- No authority grant (`authority_granted: false`).
- G4 requires exact current PR head binding; G5/G6 applicability enforced.

## Dependencies
- Depends on SCRUM-187, SCRUM-184, SCRUM-188 (all Done).
