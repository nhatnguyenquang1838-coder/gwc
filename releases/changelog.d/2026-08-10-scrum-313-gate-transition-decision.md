# Gate transition decision node maturity (SCRUM-313)

Task: `SCRUM-313`

- Closes the `gate_authority.gate-transition-decision` node maturity gap by enriching the catalog descriptor with `intent`, `outcome`, `constraints`, `exclusions`, `entry_guards`, `source_resolution`, and a closed `reason_codes` taxonomy.
- Adds the closed runtime contract schema `schemas/node-architect/gate-authority/gate-transition-decision.schema.json` covering the `decide_gate_transition` evaluator output (PASS / BLOCK / CONTINUE / AWAITING_APPROVAL) with deterministic `decision_digest`.
- `source_resolution.evaluator` binds to the existing pure, replay-safe evaluator `tools/node_architect/gate_transition_decision.py`; the node never performs the transition and grants no gate authority.
- Updates `node-registry.json` provenance `source_sha` for the descriptor.
- This change grants no protected-branch write, merge, deploy, release, production configuration, credential, migration, or production-data authority.
