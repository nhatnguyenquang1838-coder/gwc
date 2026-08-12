# SCRUM-309 — gate_authority.approval-command-validation maturity / instruction / executable

## Status
Maturing the `gate_authority.approval-command-validation` node to full
descriptor + schema + executable + focused-test maturity (MAT-F2-N03).

## Context
SCRUM-308 enriched the sibling `gate_authority.approval-token-generation`
node descriptor with intent, outcome, constraints, exclusions, entry guards,
source resolution, and a closed reason-code taxonomy, and corrected the
generated command to canonical grammar (`approval_request_id` + 16-hex
`scope_hash_short`). The `approval-command-validation` descriptor was left at
the minimal SCRUM-186 shape (description only). SCRUM-309 completes the
maturity gap for the validation side of the authority chain.

## Changes
- Enrich `core/node-architect/node-catalog/gate_authority/approval-command-validation.node.json`
  with `intent`, `outcome`, `constraints`, `exclusions`, `entry_guards`,
  `source_resolution` (binding evaluator + `schemas/gate-approval-validation.schema.json`),
  and a closed `reason_codes` taxonomy covering all validator outcomes.
- Update `core/node-architect/node-registry.json` provenance `source_sha` for the
  enriched descriptor.
- Extend `tests/test_gate_authority_approval_command_validation_m5.py` with
  `TestSchemaConformance`: schema-conformance validation of VALID, INVALID, and
  BLOCKED results against `gate-approval-validation.schema.json`, plus an
  explicit assertion that all `*_authority_granted` flags are const-false.
- No change to `tools/node_architect/approval_command_validation.py` — the
  validator logic is verified-reuse; this task adds descriptor + schema
  conformance coverage only.

## Outcome
No execution, merge, deploy, release, migration, credential, or production-data
authority is granted. The validator remains pure and fail-closed.

## References
- GitHub #244 — node: gate_authority.approval-command-validation maturity/instruction/executable
- Jira SCRUM-309
- Parent run: SCRUM-288-NA81-20260811-R4
- Authority: AR-SCRUM288-20260811-R4
