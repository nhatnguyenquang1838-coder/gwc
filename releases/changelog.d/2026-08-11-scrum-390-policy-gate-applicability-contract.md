# SCRUM-390 — Policy contract + gate applicability hardening (P0-B)

- Generalized the gate-applicability Policy contract: `required_evidence`,
  `evidence_must_be_bound`, `prohibitions`, `authority` (allowed sources/types
  + defaults), `context_requirements` (required fields, expected context
  digest, max context age) and per-decision `terminal_effect`.
- Decision artifact upgraded to `schema_version 1.1`: now binds
  run/task/repository, flow profile id/version/digest, policy registry
  ref/digest, policy id/version/digest, required evidence, prohibitions,
  resolved authority source/type, terminal effect, context digest and
  decision digest.
- Evaluator remains pure, deterministic and controller-agnostic: no
  `if autonomous`, no route- or task-specific branch. Route behaviour is
  expressed entirely in policy data plus runtime context.
- Fail-closed reason codes added: `GATE_NOT_CANONICAL`,
  `GATE_POLICY_UNVERSIONED`, `CONTEXT_BINDING_INCOMPLETE`,
  `CONTEXT_DIGEST_MISMATCH`, `CONTEXT_STALE`, `CONTEXT_FRESHNESS_UNKNOWN`,
  `EVIDENCE_BINDING_MISSING`, `EVIDENCE_BINDING_UNSATISFIED`,
  `AUTHORITY_SOURCE_UNRESOLVED`, `AUTHORITY_SOURCE_NOT_PERMITTED`,
  `AUTHORITY_TYPE_NOT_PERMITTED`.
- `NOT_APPLICABLE` is explicit skip evidence with its own terminal effect and
  is never an implicit PASS.
- New focused E2E suite `tests/test_gate_applicability_policy_contract.py`
  (26 tests) covering authority/evidence/prohibition/terminal semantics,
  digest binding, replay determinism and fail-closed paths.

No workflow ordering/DAG change, no cross-layer compiler change, no new
canonical node, no change to the active authority policy activation.
