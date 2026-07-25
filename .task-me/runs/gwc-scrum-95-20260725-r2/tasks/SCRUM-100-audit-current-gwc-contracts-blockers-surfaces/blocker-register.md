# Blocker Register

## B-01 — LIFECYCLE_STATE_MAP_INCOMPLETE

- **Severity:** `BLOCKER`
- **Recommended owner:** `SCRUM-103`
- **Finding:** gate-transition-map.yaml omits explicit G4/G5/G6 progression and terminates at completed after validation passed.
- **Required remediation:** Introduce a versioned transition/state model that preserves G3 validation, G4 merge, G5 post-merge verification and conditional G6 separately.

## B-02 — ACTION_AUTHORITY_VALIDATOR_MISSING

- **Severity:** `BLOCKER`
- **Recommended owner:** `SCRUM-103`
- **Finding:** tools/validate_gate_action.py is referenced by contract but absent.
- **Required remediation:** Implement fail-closed validation for task, repository, base/head SHA, action, gate, scope hash, expiry, actor and evidence readback.

## B-03 — PLAN_BASE_BINDING_STALE

- **Session status:** `RESOLVED_FOR_G2` through exact current-base blob rebind; checked-in source artifact remains stale and should be corrected by SCRUM-103.
- **Severity:** `BLOCKER`
- **Recommended owner:** `SCRUM-100`
- **Finding:** SCRUM-95 plan validation is bound to d33ab8… instead of current main.
- **Required remediation:** Refresh validation evidence against 82755198c772cdba7b07ebaa5fc7e8c1801a6bb0 and bind the exact current plan revision.

## B-04 — CHECKPOINT_PERSISTENCE_UNVERIFIED

- **Severity:** `MAJOR`
- **Recommended owner:** `SCRUM-103`
- **Finding:** Checkpoint/resume validation exists without verified durable persistence and resume execution.
- **Required remediation:** Define canonical store/write/read/CAS/lease/resume surfaces or explicitly keep this contract-only.

## B-05 — G5_EXECUTABLE_RESOLVER_MISSING

- **Severity:** `BLOCKER`
- **Recommended owner:** `SCRUM-103`
- **Finding:** G5 resolver behavior is contract-only.
- **Required remediation:** Implement exact-merge-SHA run discovery with known-run and combined-status fallbacks, checkpointing and evidence validation.

## B-06 — CONNECTOR_OBSERVABILITY_INCOMPLETE

- **Severity:** `BLOCKER`
- **Recommended owner:** `SCRUM-103`
- **Finding:** Current connector could not expose exact main push workflow runs or commit checks.
- **Required remediation:** Add or document a legal exact-SHA lookup route and persist known run IDs before G5.

## B-07 — PACKAGE_BASELINE_DRIFT

- **Severity:** `MAJOR`
- **Recommended owner:** `SCRUM-103`
- **Finding:** TREE.txt and BUNDLE-REPORT.json are stale against current repository content; bundle report excludes the current GWC package and carries an obsolete canonical-policy hash.
- **Required remediation:** Use one inspected refresh command and CI drift test for package manifest, tree, checksums and release/bundle metadata.

## B-08 — BUILD_REPRODUCIBILITY_SPLIT

- **Severity:** `MAJOR`
- **Recommended owner:** `SCRUM-103`
- **Finding:** build_project_package.py injects current time and git-derived identity; export_project_package.py supports fixed generated_at but the two paths are not one canonical reproducible pipeline.
- **Required remediation:** Select one canonical export path with explicit source SHA and fixed/normalized timestamp for reproducibility tests.

## B-09 — FORMAL_G01_VALIDATOR_NOT_EXECUTED

- **Status:** `RESOLVED`
- **Resolution:** Exact checked-in validator and schemas were materialized with matching Git blob hashes; validator returned exit code `0` and `PASS`.
- **Severity:** `BLOCKER`
- **Recommended owner:** `SCRUM-100`
- **Finding:** The initial connector session exposed no connector-to-local file bridge and runtime network retrieval was unavailable.
- **Required remediation:** Completed through exact connector source materialization and protected-base validation.

## B-10 — WORK_TRACKING_CONTRACT_MISMATCH

- **Severity:** `MAJOR`
- **Recommended owner:** `SCRUM-103`
- **Finding:** Repository transition authority points to ds-mcp-state-engine while the active GWC profile uses Jira MCP; Jira status is In Progress with generic transitions.
- **Required remediation:** Define a canonical mapping/adaptor that keeps Jira projection non-authoritative and records readback without conflating Jira status with gate authority.
