# Package export entry-schema-validation node (SCRUM-288)

Task: `SCRUM-288`

- Adds `package_export.entry-schema-validation` node with closed 8-reason-code taxonomy (ENTRY_SCHEMA_VALID, ENTRY_SCHEMA_INVALID, ENTRY_REQUIRED_FIELD_MISSING, ENTRY_TYPE_INVALID, ENTRY_ID_INVALID, ENTRY_UNKNOWN_FIELD, ENTRY_VERSION_UNSUPPORTED, ENTRY_DUPLICATE_ID).
- Adds node-instruction contract (`core/node-architect/node-instructions/package_export/entry-schema-validation.node-instruction.yaml`) constraining execution and forbidding grant of G2/G3/G4/G5/G6 authority.
- Adds evaluator, schema, and focused tests for entry schema validation.
- Fixes `node_id` format across all 9 `package_export` catalog descriptors from `package-export-<stem>` to `package_export.<stem>` to match the canonical format in `node-registry.json` and `node-instruction.schema.json`.
- Enriches the entry-schema-validation catalog descriptor with maturity fields (intent, outcome, constraints, exclusions, entry_guards, source_resolution, reason_codes).
- Updates `validate_node_catalog_package_export.py` with `RUNTIME_CONTRACTS` binding and `validate_runtime_contracts()` for the entry-schema-validation node.
- Updates `node-registry.json` provenance SHAs, `gate-node-route-profile.json` with `g2-validate-entry-schema` route, and `package.yaml` export entries.
- This change grants no protected-branch write, merge, deploy, release, production configuration, credential, migration, or production-data authority.
