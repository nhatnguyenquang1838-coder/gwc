# SCRUM-239 G2 handoff

## Status

- Repository: `nhatnguyenquang1838-coder/gwc`
- Base: `main@b9c6dddf3da4394cc0f3d52e030aeaecf4f5d380`
- Branch: `codex/scrum-239-crash-checkpoint-recovery-m5-20260730`
- Node: `failure_recovery.crash-checkpoint-recovery`
- Approval: `CP-20260730-239-G2-R1`
- Scope hash prefix: `42793641d2d5dd38`

## Objective

Implement the crash-checkpoint recovery M5 replay-safe slice. The node must resume only from canonical checkpoint/readback evidence and must not create duplicate effects after a crash.

## Acceptance criteria

- deterministic event replay;
- pending-action reconciliation is explicit;
- no duplicate effect after crash/resume;
- crash-point fixtures/tests pass;
- exact-head CI passes after PR.

## Boundaries

No merge, deploy, release, production/config/data/secret/credential/migration, force-push, branch deletion, history rewrite, PR-base change, scope expansion, or unrelated cleanup.
