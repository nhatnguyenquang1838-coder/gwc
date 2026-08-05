# SCRUM-188 implementation requirements

- Add `schemas/authority-boundary-decision.schema.json`.
- Add pure evaluator `tools/node_architect/authority_boundary_check.py` with the Jira-specified keyword-only interface.
- Add focused M5 tests at `tests/test_gate_authority_authority_boundary_check_m5.py`.
- Preserve canonical action-to-minimum-gate mappings, fail-closed precedence, replay/idempotency semantics, exact task/repository/scope/base/head bindings, and false authority fields.
- Keep approval generation/validation, state transitions, connector calls, Git/PR actions, deploy, release, migration, credentials, secrets, and production operations out of scope.
