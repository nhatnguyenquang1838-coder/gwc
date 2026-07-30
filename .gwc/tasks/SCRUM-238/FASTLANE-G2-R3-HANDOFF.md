# SCRUM-238 Fastlane G2 R3 handoff

## Status

- Repository: `nhatnguyenquang1838-coder/gwc`
- Base: `main@3b0938065e71e699d327d041f5b6023ed30a29dc`
- Branch: `codex/scrum-238-timeout-recovery-m5-fastlane-r3-20260730`
- Node: `failure_recovery.timeout-recovery`
- Approval: `CP-20260730-238-G2-R3`
- Scope hash: `sha256:3123425c4076103ca579c6757f46e37b81e55d4096213735d8dd8159b67bc2ea`
- Dependencies: `SCRUM-203`, `SCRUM-198`
- Implementation in this commit: `NOT_STARTED`

The prior R2 approval bound to `main@1db5cdde7666e95e0a5d864633a3255a2a6ad40e` is invalid and must not be reused.

## Worker prompt

```text
SOURCE INSTRUCTION: REPO
EXECUTION MODE: local_agent or chat_connector_only according to verified capabilities
Task: SCRUM-238
Repository: nhatnguyenquang1838-coder/gwc

Read AGENTS.md, core/Coding_Project_Governance_v1.0.md, core/GATE_LIFECYCLE_CONTRACT_v1.0.md,
projects/gwc/project-profile.yaml, projects/gwc/project-instructions.md, projects/gwc/project-extension.md,
this handoff, and .gwc/tasks/SCRUM-238/g2/execution-envelope.yaml.

Before implementation, re-read current main. Continue only if main is still:
3b0938065e71e699d327d041f5b6023ed30a29dc

Materialize task-scoped G0/G1/G2 under .gwc/tasks/SCRUM-238, run:
python tools/validate_g01.py --workspace .gwc/tasks/SCRUM-238 --gate G2_EXECUTION --json

Require PASS. Check SCRUM-203 and SCRUM-198 evidence or record dependency wait. Then implement only approved
paths for timeout-recovery, validate no-blind-retry on unknown effects, bounded retry checkpoints,
deterministic reason codes, and replay-stable decisions. Push guarded branch and stop at G2 exit.
Draft PR belongs to G3. No merge, deploy, release, production/config/data/secret/credential/migration,
force-push, branch deletion, history rewrite, PR-base change, scope expansion, or unrelated cleanup.
```
