# Evidence and Provenance Map

## Root binding

- Repository: `nhatnguyenquang1838-coder/gwc`
- Default branch: `main`
- Exact main SHA: `82755198c772cdba7b07ebaa5fc7e8c1801a6bb0`
- Planning merge: PR `#96`
- Jira projection: `SCRUM-100`, status `In Progress`, parent `SCRUM-95`, blocks `SCRUM-103`

## Plan binding

- Current Kiro file blob set:
  - `.kiro/specs/GWC-P1-architecture-readiness-canonical-registry/requirements.md` → `05192d267055d106dd20d6df517aca505a4c7aa2`
  - `.kiro/specs/GWC-P1-architecture-readiness-canonical-registry/design.md` → `3102379d5525ef822def867e621fe7a845a79fcf`
  - `.kiro/specs/GWC-P1-architecture-readiness-canonical-registry/tasks.md` → `07f6332c70274d2eacb415521f1b4e9f093dc37d`
- Current local binding revision: `sha256:f72746ea784e9460b218e26b01c652240a458a41c3f85483dc614c1c3ac5eb6a`
- Existing Task-Me validation revision: `sha256:25cdc71ffdee27f684263db8e2d039e5d4d46aed4a5068be6d8d0e85826281d4`
- Existing Task-Me protected base: `d33ab8a52d341fa7f9ae65a1a88cb193ba61aded`
- Checked-in validation classification: `STALE`
- Governed current-base session binding: `PASS` (`sha256:f72746ea784e9460b218e26b01c652240a458a41c3f85483dc614c1c3ac5eb6a`)

## Source map

- `.github/workflows/validate-instructions.yml`
- `.gwc/tasks/**`
- `.task-me/runs/gwc-scrum-95-20260725-r2/_shared/08-plan-validation.json`
- `.task-me/runs/gwc-scrum-95-20260725-r2/_shared/09-baseline-refresh.json`
- `.task-me/runs/gwc-scrum-95-20260725-r2/_shared/10-restart-validation.json`
- `AGENTS.md`
- `BUNDLE-REPORT.json`
- `SHA256SUMS.txt`
- `TREE.txt`
- `core/E2E_DRAFT_PR_DELIVERY_RULE.md`
- `core/G5_CI_VERIFICATION_CONTRACT_v1.0.md`
- `core/GATE_LIFECYCLE_CONTRACT_v1.0.md`
- `core/RUNTIME_CATALOG_KNOWLEDGE_GRAPH_CONTRACT_v1.0.md`
- `core/node-architect/CHECKPOINT_RESUME_RULE_v0.1.md`
- `core/node-architect/CONSUMER_PACKAGE_EXPORT_RULE_v0.1.md`
- `core/node-architect/node-catalog-expansion-plan.json`
- `core/node-architect/node-catalog/**`
- `core/node-architect/node-catalog/gate_authority/authority-boundary-check.node.json`
- `core/runbooks/GATE_G0_G1_OPERATIONAL_RUNBOOK_v1.0.md`
- `core/task-lifecycle/gate-transition-map.yaml`
- `projects/gwc/package.yaml`
- `schemas/approval-envelope.schema.json`
- `schemas/g0-context-snapshot.schema.json`
- `schemas/g1-decision-record.schema.json`
- `schemas/g1-intake-brief.schema.json`
- `schemas/g1-options.schema.json`
- `schemas/g1-preflight-report.schema.json`
- `schemas/g3-delivery-record.schema.json`
- `schemas/g5-ci-verification-evidence.schema.json`
- `schemas/node-architect/checkpoint.schema.json`
- `schemas/node-architect/resume-token.schema.json`
- `schemas/node-architect/runtime-catalog-taxonomy.schema.json`
- `tests/test_g3_delivery.py`
- `tests/test_runtime_catalog_taxonomy_kg.py`
- `tools/build_project_package.py`
- `tools/capture_g01_decision.py`
- `tools/export_project_package.py`
- `tools/generate_g01_runtime.py`
- `tools/node_architect/project_runtime_knowledge_graph.py`
- `tools/node_architect/validate_checkpoint_resume.py`
- `tools/node_architect/validate_node_registry.py`
- `tools/validate_g01.py`
- `tools/validate_g3_delivery.py`
- `tools/verify_package_export_smoke.py`

## Gate status refresh

- Exact G0/G1 validator: `PASS`, exit code `0`.
- G1 decision: `ACCEPTED`.
- Active G2 approval: `APPROVE_G2_EXECUTION_SCRUM-100_20260725T172050Z`.
- Guarded branch: `docs/SCRUM-100-current-state-audit`.
- Write boundary: audit artifacts only; no runtime, validator, workflow or package modification.

## Evidence authority

- GitHub repository content at the exact SHA is code/contract/package/CI-definition truth.
- GWC task workspace artifacts are gate/evidence truth.
- Jira is a projection and does not grant G2–G6 authority.
- Generated graphs and package reports are derived evidence and may be stale.

## Projection event

- Jira transition: `To Do → In Progress`
- Comment ID: `10121`
- Source of truth: `false`
