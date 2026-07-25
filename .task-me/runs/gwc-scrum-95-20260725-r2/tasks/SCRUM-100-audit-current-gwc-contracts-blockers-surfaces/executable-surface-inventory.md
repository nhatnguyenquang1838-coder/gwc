# Executable-Surface Inventory

## G0-G6 lifecycle contract coverage

- **Classification:** `PARTIAL`
- **Finding:** All seven gates are documented, but executable enforcement is uneven and the state transition map does not represent the full sequence.
- **Evidence:**
  - `core/GATE_LIFECYCLE_CONTRACT_v1.0.md`
  - `core/runbooks/GATE_G0_G1_OPERATIONAL_RUNBOOK_v1.0.md`
  - `core/task-lifecycle/gate-transition-map.yaml`

## G0/G1 artifact generation and validation

- **Classification:** `IMPLEMENTED`
- **Session verification:** exact checked-in validator returned exit code `0`, `PASS`, with matching validator/schema Git blob hashes.
- **Finding:** Canonical schemas, generator, decision capture and `validate_g01.py` exist. This session materialized the exact connector-returned validator and schemas, verified their Git blob hashes, and obtained exit code `0` with `PASS`.
- **Evidence:**
  - `tools/generate_g01_runtime.py`
  - `tools/capture_g01_decision.py`
  - `tools/validate_g01.py`
  - `schemas/g0-context-snapshot.schema.json`
  - `schemas/g1-intake-brief.schema.json`
  - `schemas/g1-preflight-report.schema.json`
  - `schemas/g1-options.schema.json`
  - `schemas/g1-decision-record.schema.json`

## G2 execution-envelope enforcement

- **Classification:** `PARTIAL`
- **Finding:** validate_g01.py can require a G2 artifact and plan-read receipt, but no repository-backed general action-authority validator was found.
- **Evidence:**
  - `tools/validate_g01.py`
  - `schemas/approval-envelope.schema.json`
  - `core/GATE_LIFECYCLE_CONTRACT_v1.0.md`

## G3 exact-head delivery review

- **Classification:** `IMPLEMENTED`
- **Finding:** A dedicated G3 delivery validator checks Draft PR state, exact head SHA, scope hash, independent review lanes, CI requirements and later-gate exclusions.
- **Evidence:**
  - `tools/validate_g3_delivery.py`
  - `schemas/g3-delivery-record.schema.json`
  - `tests/test_g3_delivery.py`
  - `core/E2E_DRAFT_PR_DELIVERY_RULE.md`

## G3, G4 and G5 separation

- **Classification:** `PARTIAL`
- **Finding:** Contracts separate validation, merge and post-merge verification; the current transition map sends VALIDATION_PASSED directly to completed and has no explicit G4/G5 states.
- **Evidence:**
  - `core/GATE_LIFECYCLE_CONTRACT_v1.0.md`
  - `core/E2E_DRAFT_PR_DELIVERY_RULE.md`
  - `core/task-lifecycle/gate-transition-map.yaml`

## Action-authority validator

- **Classification:** `BLOCKED`
- **Finding:** Contracts require tools/validate_gate_action.py, but the path is absent. Node descriptors and structural registry checks do not enforce exact task/repository/SHA/scope/expiry/action authority.
- **Evidence:**
  - `core/GATE_LIFECYCLE_CONTRACT_v1.0.md`
  - `core/node-architect/node-catalog/gate_authority/authority-boundary-check.node.json`
  - `tools/node_architect/validate_node_registry.py`
  - `MISSING: tools/validate_gate_action.py`

## Checkpoint and resume

- **Classification:** `PARTIAL`
- **Finding:** Rule, schemas and pair validator exist; no durable persistence/resume service or authoritative checkpoint store was verified in the repository.
- **Evidence:**
  - `core/node-architect/CHECKPOINT_RESUME_RULE_v0.1.md`
  - `schemas/node-architect/checkpoint.schema.json`
  - `schemas/node-architect/resume-token.schema.json`
  - `tools/node_architect/validate_checkpoint_resume.py`

## Task workspace and evidence persistence

- **Classification:** `PARTIAL`
- **Finding:** The canonical .gwc/tasks/<task-id> layout is enforced by current contracts and validators, but legacy workspaces remain and work-tracking transition authority still points to ds-mcp-state-engine.
- **Evidence:**
  - `AGENTS.md`
  - `core/runbooks/GATE_G0_G1_OPERATIONAL_RUNBOOK_v1.0.md`
  - `core/task-lifecycle/gate-transition-map.yaml`
  - `.gwc/tasks/**`

## Consumer package export

- **Classification:** `PARTIAL`
- **Finding:** Package definitions, deterministic file hashing, export safety checks and smoke tooling exist; generated metadata and checked-in bundle/tree reports are not one reproducible current baseline.
- **Evidence:**
  - `projects/gwc/package.yaml`
  - `tools/build_project_package.py`
  - `tools/export_project_package.py`
  - `tools/verify_package_export_smoke.py`
  - `BUNDLE-REPORT.json`
  - `TREE.txt`
  - `SHA256SUMS.txt`

## CI execution

- **Classification:** `IMPLEMENTED`
- **Finding:** The validation workflow runs instruction validation, all unit tests, Python compilation and artifact upload on pull requests and pushes to main.
- **Evidence:**
  - `.github/workflows/validate-instructions.yml`

## CI connector observability for exact main SHA

- **Classification:** `BLOCKED`
- **Finding:** No combined statuses or connector-visible workflow runs were returned for current main. This is observability incomplete, not a pass/fail conclusion.
- **Evidence:**
  - `GitHub.get_commit_combined_status(82755198…): statuses=[]`
  - `GitHub.fetch_commit_workflow_runs(82755198…): workflow_runs=[]`
  - `core/G5_CI_VERIFICATION_CONTRACT_v1.0.md`

## G5 exact-merge-SHA resolver

- **Classification:** `CONTRACT_ONLY`
- **Finding:** A detailed resolver/checkpoint/evidence contract exists, but no executable resolver or dedicated G5 validator was verified.
- **Evidence:**
  - `core/G5_CI_VERIFICATION_CONTRACT_v1.0.md`
  - `schemas/g5-ci-verification-evidence.schema.json`

## 81 catalog slots

- **Classification:** `PROPOSED`
- **Finding:** Nine families and 81 descriptor slots are present/package-listed, but the expansion plan remains plan_only with implementation_allowed=false.
- **Evidence:**
  - `core/node-architect/node-catalog-expansion-plan.json`
  - `core/node-architect/node-catalog/**`
  - `projects/gwc/package.yaml`

## Four explicit runtime nodes

- **Classification:** `PARTIAL`
- **Finding:** The KG projector explicitly emits four runtime-node identities and relationships. They are projection descriptors, not verified executable adapters.
- **Evidence:**
  - `tools/node_architect/project_runtime_knowledge_graph.py`

## 116 edge scenarios

- **Classification:** `CONTRACT_ONLY`
- **Finding:** The number 116 is asserted in a taxonomy test fixture. No canonical registry of 116 scenario definitions was verified.
- **Evidence:**
  - `tests/test_runtime_catalog_taxonomy_kg.py`
  - `schemas/node-architect/runtime-catalog-taxonomy.schema.json`

## Runtime knowledge graph

- **Classification:** `PARTIAL`
- **Finding:** The projector emits 4 runtime nodes, 3 scenario nodes and 13 graph edges. Graph-edge count is not the edge-scenario count.
- **Evidence:**
  - `tools/node_architect/project_runtime_knowledge_graph.py`
  - `core/RUNTIME_CATALOG_KNOWLEDGE_GRAPH_CONTRACT_v1.0.md`

## SCRUM-95 planning package binding

- **Classification:** `STALE_SOURCE_ARTIFACT / REFRESHED_SESSION_BINDING`
- **Finding:** The checked-in validation evidence remains bound to `d33ab8…` and revision `sha256:25cdc7…`. For this governed session, unchanged plan blobs were verified and rebound to current main `82755198…` as `sha256:f72746…`; this does not claim Task-Me was rerun.
- **Evidence:**
  - `.task-me/runs/gwc-scrum-95-20260725-r2/_shared/08-plan-validation.json`
  - `.task-me/runs/gwc-scrum-95-20260725-r2/_shared/09-baseline-refresh.json`
  - `.task-me/runs/gwc-scrum-95-20260725-r2/_shared/10-restart-validation.json`

## Consumer-package/runtime boundary

- **Classification:** `IMPLEMENTED`
- **Finding:** Package notes repeatedly exclude runtime engine, scheduler/worker, merge, deploy and production authority. Exported node catalogs are governance descriptors and tools, not a durable runtime.
- **Evidence:**
  - `projects/gwc/package.yaml`
  - `core/node-architect/CONSUMER_PACKAGE_EXPORT_RULE_v0.1.md`
