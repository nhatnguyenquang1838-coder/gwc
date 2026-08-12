# Approval token generation node maturity (SCRUM-308)

Task: `SCRUM-308`

- Closes the `gate_authority.approval-token-generation` maturity gap by enriching the catalog descriptor with intent, typed outcome, fail-closed constraints, exclusions, entry guards, executable source resolution, and a closed reason-code taxonomy.
- Adds the closed runtime contract schema `schemas/node-architect/gate-authority/approval-token-generation.schema.json` for the deterministic, replay-safe `generate_approval_request` evaluator.
- Binds the node to `tools/node_architect/approval_token_generation.py`; the evaluator generates a canonical approval_command following the grammar `APPROVE <GATE_SHORT> <approval_request_id> <scope_hash_short:16hex> <expires_at_utc>` and never grants authority.
- Corrects the generated command to canonical grammar: replaces task_id with a deterministic, lowercase, schema-valid `approval_request_id`, and binds `scope_hash_short` (first 16 hex of scope_hash) instead of the full 64-hex token.
- Preserves the full 64-hex `approval_token` as non-secret integrity evidence in the payload, but never in the human command.
- Updates `node-registry.json` provenance `source_sha` for the descriptor.
- This change grants no protected-branch write, merge, deploy, release, production configuration, credential, migration, or production-data authority.
