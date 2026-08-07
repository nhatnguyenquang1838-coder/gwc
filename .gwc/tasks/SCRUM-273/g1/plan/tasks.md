# SCRUM-273 — Tasks

Ordered sub-task decomposition (see g1/decision decision.subagent_distribution_plan).

- [ ] SUB-TASK-1: Author request + result schemas
  `schemas/node-architect/ai-task-execution-request.schema.json`,
  `schemas/node-architect/ai-task-execution-result.schema.json`.
  Fields exactly per design.md. `additionalProperties: false`, version `1.0`.

- [ ] SUB-TASK-2: Instruction pack builder
  `tools/node_architect/build_node_instruction_pack.py` — composes typed pack from
  task + repo context + G0/G1 decision + scope + route + validation plan; provider-neutral.

- [ ] SUB-TASK-3: Provider-neutral adapter
  `tools/node_architect/ai_agent_adapter.py` — `Provider` protocol, `CustomRunnerProvider`,
  `DeterministicFakeProvider`, `execute(...)` with scope enforcement, idempotency/replay,
  bounded repair, fail-closed, `g3_g4_g5_authority_granted: false`, no manual fallback.

- [ ] SUB-TASK-4: Result validator
  `tools/node_architect/validate_ai_agent_result.py` — schema + scope-envelope validation.

- [ ] SUB-TASK-5: Tests
  `tests/test_ai_agent_adapter.py` — deterministic fake + AC-1..AC-6 fixtures
  (out-of-scope, malformed, timeout, duplicate/replay, no-fallback, no-G3/G4/G5).

- [ ] SUB-TASK-6: Red→green validation
  Run isolated venv validator + `PYTHONPATH=. python3 -m unittest tests.test_ai_agent_adapter`
  + ensure existing client_runtime/checkpoint suites stay green (AC-6).

## Dependency order
SUB-TASK-1 → SUB-TASK-2 → SUB-TASK-3 → SUB-TASK-4 → SUB-TASK-5 → SUB-TASK-6.
