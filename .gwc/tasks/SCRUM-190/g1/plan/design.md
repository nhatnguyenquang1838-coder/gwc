# SCRUM-190 — Design (Task Me plan)

## Files created

1. `schemas/gate-transition-decision.schema.json`
   - Closed JSON Schema (`additionalProperties: false` at every object level).
   - Top-level: `schema_version`, `artifact_type`, `generated_at`, `trace`, `binding`,
     `current_node`, `decision`, `next_node`, `evidence`, `replay`, `status`.
   - `decision.outcome` enum: `PASS`, `BLOCK`, `CONTINUE`, `AWAITING_APPROVAL`, `NOT_APPLICABLE`.
   - `next_node` is either a resolved node identifier from the transition map or `null` with a
     required `reason_code`.

2. `tools/node_architect/gate_transition_decision.py`
   - Pure function `decide_gate_transition(current_state, gate_evidence, transition_map)`.
   - Steps: validate inputs → bind task/repository/base/scope identity → apply outcome precedence →
     resolve next node from the map → compute replay digest → emit decision or refusal.
   - Outcome precedence (fail closed, first match wins): invalid/missing binding → `BLOCK`;
     gate not applicable → `NOT_APPLICABLE`; human approval required and unbound →
     `AWAITING_APPROVAL`; gate work incomplete → `CONTINUE`; all evidence satisfied → `PASS`.
   - Refusal codes: `BINDING_MISSING`, `EVIDENCE_INVALID`, `SCOPE_DRIFT`, `MAP_NODE_UNKNOWN`,
     `TRANSITION_NOT_PERMITTED`.
   - Transition map loaded from `core/task-lifecycle/gate-transition-map.yaml` and treated as the
     single source of topology.
   - Replay digest: SHA-256 over canonical JSON (sorted keys) of the decision minus the digest field.
   - No I/O beyond reading the provided map, no subprocess, no network, no state mutation.

3. `tests/test_gate_authority_gate_transition_decision_m5.py`
   - Coverage: every outcome value, precedence ordering, map-driven next-node resolution,
     unknown-node refusal, drift/refusal paths, no-transition invariant, replay digest stability.

## Out of scope

Registry/descriptor wiring, connector calls, approval generation, applying a transition,
Draft PR, merge, deploy, release, migration, credentials, or production data.
