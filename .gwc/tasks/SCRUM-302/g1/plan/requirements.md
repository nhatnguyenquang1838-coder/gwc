# SCRUM-302 Requirements

## Goal

Implement the `intake_context.risk-classification` read-only evaluator on the
exact protected execution base `pre-prod@7f1d26e4fb0d4d09c49e9952994220a2f47a3824`.

## Requirements

1. Complete, verified risk inputs SHALL produce a deterministic typed
   `risk-profile` result containing risk level, flags, required gate, reason
   codes, policy provenance, source bindings, and a decision digest.
2. Missing, unknown, stale, ambiguous, conflicting, or malformed inputs SHALL
   return `BLOCKED` or `HUMAN_REQUIRED`; no unknown state may map to low risk or
   an accepted result.
3. A policy/version mismatch SHALL invalidate the classification and require
   recomputation rather than reusing a stale result.
4. A higher risk level SHALL tighten downstream controls or required gates and
   SHALL never set write, merge, deployment, or production authority true.
5. The contract SHALL be closed by JSON Schema and bound in the
   `intake_context` runtime-contract validator.
6. Focused, negative, replay/determinism, policy-drift, authority-negative,
   neighbor, and family-validator tests SHALL cover the implementation.

## Exclusions

- No autonomous-preprod manifest or authority-plane change.
- No direct `pre-prod` or `main` write.
- No merge, auto-merge, deployment, release, credentials, secrets, migration,
  or production-data operation.
