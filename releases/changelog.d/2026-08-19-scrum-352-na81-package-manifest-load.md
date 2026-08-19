feat(gwc): SCRUM-352 NA81-F7-N01 package-manifest-load maturity/instruction/executable

Recertify the existing `package_export.package-manifest-load` gate
(SCRUM-229) under the NA81 autonomous lane (DELTA_REQUIRED):

- The node instruction card
  `core/node-architect/node-instructions/package_export/package-manifest-load.node-instruction.yaml`
  already exists and matches the NA81 package_export gate-instruction contract
  (entry-conditions, closed forbidden_actions, evidence/logs required, retry
  idempotency + pending reconciliation, rollback strategy, explicit
  authority_boundary with no G2/G3/G4/G5/G6, and pass->entry-schema-validation
  routing). It is left unchanged for this recert (no re-add, provenance intact).
- The node executable
  `tools/node_architect/package_export/package_manifest_load.py`
  (pure, deterministic, fail-closed manifest loader) already exists and is
  unchanged for this recert.
- Add a dedicated NA81 recert test
  `tests/package_export/test_package_manifest_load_na81.py` bound to the exact
  module `node_architect.package_export.package_manifest_load`, covering: safe
  load across source XOR source_path modes, the closed reason-code taxonomy for
  blocking (missing/ambiguous source, parse error, missing/unsupported schema
  version, missing/empty instructions, duplicate entry id, incomplete/invalid
  binding, missing/observed-sha mismatch, package-version mismatch),
  determinism (stable manifest_digest and replay identity, field-order
  independent, entry-order preserved), normalization, no authority granted
  (authority_granted always False; observed_source_sha never stored),
  idempotent replay vs semantic conflicts (payload / source_ref), and
  fail-closed schema-validation-unavailable. 32 recert scenarios pass; the
  broader `tests/package_export/` suite and full repo suite remain green.
- Node is already registered in `core/node-architect/node-registry.json` and
  exported via `projects/gwc/package.yaml` (catalog, instruction, evaluator,
  result schema, and base test entries present).

No `*.node.json` `description`/`source` fields edited (provenance trap avoided).

Parent authority: AR-SCRUM288-RECERT-20260814-R10 (issue #232), task SCRUM-352.
Targets pre-prod only; main is FORBIDDEN.
