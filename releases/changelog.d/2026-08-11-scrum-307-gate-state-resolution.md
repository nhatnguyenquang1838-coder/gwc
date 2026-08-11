# Gate state resolution node maturity (SCRUM-307)

Task: `SCRUM-307`

- Closes the `gate_authority.gate-state-resolution` maturity gap by enriching the catalog descriptor with intent, typed outcome, fail-closed constraints, exclusions, entry guards, executable source resolution, and a closed reason-code taxonomy.
- Adds the closed runtime contract schema `schemas/node-architect/gate-authority/gate-state-resolution.schema.json` for the existing deterministic, replay-safe `resolve_gate_state` evaluator.
- Binds the node to `tools/node_architect/gate_state_resolution.py`; the evaluator resolves state only and never performs a transition or grants authority.
- Updates `node-registry.json` provenance `source_sha` for the descriptor.
- This change grants no protected-branch write, merge, deploy, release, production configuration, credential, migration, or production-data authority.
