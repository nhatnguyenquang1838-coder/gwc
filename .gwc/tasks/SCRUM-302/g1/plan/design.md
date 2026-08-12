# SCRUM-302 Design

## Boundary

The evaluator is a pure, deterministic, read-only function in
`tools/node_architect/risk_classification.py`. It consumes explicitly supplied
typed upstream artifacts and a declared policy object. It does not query Jira,
GitHub, the filesystem, or a runtime authority service.

## Interface

`render_risk_classification(task_id, repository, base_sha, request_intake,
source_resolution, repo_identity, protected_base_snapshot, policy,
classified_at=None)` returns one closed `risk-profile` artifact.

The result includes `outcome`, `risk_level`, `risk_flags`, `required_gate`,
`additional_authority_gates`, `approval_requirements`, `reason_code`,
`reason_codes`, `source_bindings`, `policy_provenance`, `policy_version`,
`classified_at`, `decision_digest`, `read_only_projection`, and explicit false
authority fields.

## Classification rules

- Validate task, repository, 40-character base SHA, upstream artifact shape,
  verified/accepted upstream outcomes, and policy version/digest first.
- Any missing, unknown, stale, conflicting, or malformed evidence fails closed.
- Detect production, secret, destructive, migration, and release/deployment
  signals from the bounded request facts and map them to the closed reason-code
  vocabulary.
- Use a stable severity order `R3 > R2 > R1 > R0`; unknown signals produce
  `HUMAN_REQUIRED` with `RISK_UNCLASSIFIED` rather than `R0`.
- Emit a canonical digest over the normalized inputs and policy, excluding the
  timestamp and prior digest. Replaying equivalent inputs yields the same
  digest and result.
- If a prior classification carries a different policy version or digest, emit
  a stale-policy result and require recomputation.

## Integration

Add `schemas/risk-classification.schema.json` and bind the evaluator,
entrypoint, schema, and `risk-profile` artifact type in
`tools/node_architect/validate_node_catalog_intake_context.py`. Preserve the
existing nine-node catalog and read-only `G0_CONTEXT` descriptor boundary.

## Validation

Run JSON Schema validation, focused SCRUM-302 tests, adjacent intake-context
tests, the family validator, and diff/secret/scope checks at the exact branch
head derived from `pre-prod`.
