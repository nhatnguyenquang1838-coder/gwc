feat(gwc): SCRUM-355 NA81-F7-N04 target-path-safety-check maturity/instruction/executable

Recertify the existing `package_export.target-path-safety-check` gate
(SCRUM-232) under the NA81 autonomous lane (DELTA_REQUIRED):

- Add the missing node instruction card
  `core/node-architect/node-instructions/package_export/target-path-safety-check.node-instruction.yaml`
  mirroring the package_export gate-instruction contract (entry-schema-validation
  style): closed forbidden_actions, evidence/logs required, retry idempotency +
  pending reconciliation, rollback strategy, explicit authority_boundary
  (no G2/G3/G4/G5/G6), and pass->governance-tree-build routing.
- Add a dedicated NA81 recert test
  `tests/package_export/test_target_path_safety_check_na81.py` bound to the
  exact module `node_architect.package_export.target_path_safety_check`,
  covering: safe governance targets, absolute/Windows-absolute rejection,
  `..` traversal rejection, backslash rejection, root-escape rejection,
  prefix-forbidden rejection, empty rejection, duplicate + case-collision
  detection, self-copy conflict, overwrite/idempotency and unknown-readback
  blocking, deterministic digest, no filesystem side effect, and
  authority_never_granted.
- Base executable `tools/node_architect/package_export/target_path_safety_check.py`
  (pure, deterministic, fail-closed gate evaluator) is unchanged for this recert;
  17 base + recert tests pass.

No `*.node.json` `description`/`source` fields edited (provenance trap avoided).
Node is already registered in `core/node-architect/node-registry.json` and exported
via `projects/gwc/package.yaml`.

Parent authority: AR-SCRUM288-RECERT-20260814-R10 (issue #232), task SCRUM-355.
Targets pre-prod only; main is FORBIDDEN.
