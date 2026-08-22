feat(gwc): SCRUM-353 NA81-F7-N02 entry-schema-validation maturity/instruction/executable

Recertify the existing `package_export.entry-schema-validation` gate
(SCRUM-230) under the NA81 autonomous lane (DELTA_REQUIRED):

- The node instruction card
  `core/node-architect/node-instructions/package_export/entry-schema-validation.node-instruction.yaml`
  already exists and matches the NA81 package_export gate-instruction contract
  (entry-conditions, closed forbidden_actions, evidence/logs required, retry
  idempotency + pending reconciliation, rollback strategy, explicit
  authority_boundary with no G2/G3/G4/G5/G6, and pass->target-path-safety-check
  routing). It is left unchanged for this recert (no re-add, provenance intact).
- Add a dedicated NA81 recert test
  `tests/package_export/test_entry_schema_validation_na81.py` bound to the
  exact module `node_architect.package_export.entry_schema_validation`,
  covering: safe single/multi-entry validation, unknown-field (closed schema)
  rejection, missing required fields, type mismatches, invalid entry id,
  unsupported entry_version, empty path/target, duplicate-id dedupe, manifest
  structural failure, normalization/determinism, stable schema digest,
  inventory-count equals entry-count, no filesystem side effect, and
  authority_never_granted. 35 base + recert scenarios across the suite pass.
- Base executable `tools/node_architect/package_export/entry_schema_validation.py`
  (pure, deterministic, fail-closed schema gate evaluator) is unchanged for
  this recert.

No `*.node.json` `description`/`source` fields edited (provenance trap avoided).
Node is already registered in `core/node-architect/node-registry.json` and exported
via `projects/gwc/package.yaml`.

Parent authority: AR-SCRUM288-RECERT-20260814-R10 (issue #232), task SCRUM-353.
Targets pre-prod only; main is FORBIDDEN.
