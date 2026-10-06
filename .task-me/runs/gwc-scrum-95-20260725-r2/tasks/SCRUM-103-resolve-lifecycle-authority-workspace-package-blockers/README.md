# SCRUM-103 鈥?Resolve lifecycle, authority-validator, workspace and package blockers

## Objective

Implement the smallest compatible corrections required before registry/runtime expansion.

## Delivery wave

Wave 2

## Dependencies

- Requires: SCRUM-100
- Parallel with: None

## Scope

### Included

- G4/G5 lifecycle representation
- Executable action-authority validation path
- Canonical .gwc/tasks/<task-id> workspace
- G3 ready-for-review consistency
- Package/integrity drift
- G2 operational contract

### Excluded

- Adaptive graph compiler
- Durable runtime
- Production actions

## Definition of done

- No blocker-severity finding remains open.
- Current tests remain compatible or migrations are explicit.
- No G4/G5/G6 authority is weakened.
- Consumer package validation passes.

## Handoff

Read `task.yaml` first, then `implementation-plan.md`, `coding-guide.md` and `test-plan.md`. Re-verify exact protected-base paths before any G2 write.

