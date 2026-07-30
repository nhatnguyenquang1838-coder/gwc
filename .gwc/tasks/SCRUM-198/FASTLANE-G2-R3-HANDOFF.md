# SCRUM-198 Fastlane G2 R3 handoff

## Status

- Repository: `nhatnguyenquang1838-coder/gwc`
- Base: `main@3b0938065e71e699d327d041f5b6023ed30a29dc`
- Branch: `codex/scrum-198-ci-run-capture-m5-fastlane-r3-20260730`
- Node: `repo_delivery.ci-run-capture`
- Approval: `CP-20260730-198-G2-R3`
- Scope hash: `sha256:234b96f0de6a07fb7ab8c2d444ea6feeb4274230a6be3e0d530331648fd2d0f6`
- Dependency: `SCRUM-203`
- Implementation in this commit: `NOT_STARTED`

The prior R2 approval bound to `main@1db5cdde7666e95e0a5d864633a3255a2a6ad40e` is invalid and must not be reused.

## Worker prompt

```text
SOURCE INSTRUCTION: REPO
EXECUTION MODE: local_agent or chat_connector_only according to verified capabilities
Task: SCRUM-198
Repository: nhatnguyenquang1838-coder/gwc

Read AGENTS.md, core/Coding_Project_Governance_v1.0.md, core/GATE_LIFECYCLE_CONTRACT_v1.0.md,
projects/gwc/project-profile.yaml, projects/gwc/project-instructions.md, projects/gwc/project-extension.md,
this handoff, and .gwc/tasks/SCRUM-198/g2/execution-envelope.yaml.

Before implementation, re-read current main. Continue only if main is still:
3b0938065e71e699d327d041f5b6023ed30a29dc

Materialize task-scoped G0/G1/G2 under .gwc/tasks/SCRUM-198, run:
python tools/validate_g01.py --workspace .gwc/tasks/SCRUM-198 --gate G2_EXECUTION --json

Require PASS. Check that SCRUM-203 evidence exists or record dependency wait. Then implement only approved
paths for ci-run-capture, validate exact-head observation, no false PASS, pending checkpoint classification,
and head-drift invalidation. Push guarded branch and stop at G2 exit.
Draft PR belongs to G3. No merge, deploy, release, production/config/data/secret/credential/migration,
force-push, branch deletion, history rewrite, PR-base change, scope expansion, or unrelated cleanup.
```
