# SCRUM-191 — Design (Task Me plan)

## Files created

1. `schemas/g2-execution-envelope.schema.json`
   - Closed JSON Schema (`additionalProperties: false` at every object level).
   - Top-level: `schema_version`, `artifact_type`, `generated_at`, `trace`, `binding`,
     `scope`, `authority`, `lifecycle`, `replay`, `status`.
   - `binding`: F1 refs (intake, options, decision, scope hash) and F2 refs
     (authority-boundary decision, approval validation record).
   - `authority.excluded` requires the literal later-gate set.
   - `lifecycle.state` enum: `DRAFT`, `AWAITING_APPROVAL`, `ACTIVE`.

2. `tools/node_architect/g2_execution_envelope_render.py`
   - Pure function `render_g2_execution_envelope(f1_scope, f2_authority, approval=None)`.
   - Steps: validate inputs → resolve bindings → build closed scope sets →
     derive lifecycle state → compute replay digest → emit envelope or refusal.
   - Refusal codes: `SCOPE_BINDING_MISSING`, `AUTHORITY_BINDING_MISSING`,
     `SCOPE_DRIFT`, `APPROVAL_INVALID`, `ENVELOPE_NOT_CLOSED`.
   - Lifecycle rule: no approval → `DRAFT`; approval requested but unvalidated →
     `AWAITING_APPROVAL`; validated approval bound (SCRUM-186 contract) → `ACTIVE`.
   - Replay digest: SHA-256 over canonical JSON (sorted keys, no whitespace variance) of the
     envelope minus the digest field itself.
   - No I/O, no subprocess, no network.

3. `tests/test_gate_authority_g2_execution_envelope_render_m5.py`
   - Determinism (repeat render equality), closed-schema validation, F1/F2 binding fidelity,
     inactive-before-approval, later-gate exclusion invariants, drift/refusal paths,
     checkpoint/replay digest stability.

## Dependencies

SCRUM-184 … SCRUM-189, especially SCRUM-186 approval validation, which supplies the validated
approval record consumed to reach `ACTIVE`.

## Out of scope

Registry/descriptor wiring, connector calls, approval generation, execution of the envelope,
Draft PR, merge, deploy, release, migration, credentials, or production data.
