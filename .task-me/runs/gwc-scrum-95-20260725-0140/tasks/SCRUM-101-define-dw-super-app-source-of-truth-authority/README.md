# SCRUM-101 — Define DW SUPER APP source-of-truth and authority matrix

## Objective

Define the integration ownership and authority boundaries for GWC, UA, Task-Me, BMAD, GitHub/CI, deployment systems and Jira.

## Delivery wave

Wave 1

## Dependencies

- Requires: None
- Parallel with: SCRUM-100, SCRUM-102

## Scope

### Included

- Control-plane responsibilities
- Generated-output ownership
- Exact source-of-truth matrix
- Adapter read/write boundaries
- Authority and projection distinctions

### Excluded

- Implementing UA/Task-Me/BMAD integrations
- Product source changes

## Definition of done

- Source-of-truth matrix has no ownership collision.
- Every adapter has allowed writes and explicit denied writes.
- Human authority boundaries are explicit.

## Handoff

Read `task.yaml` first, then `implementation-plan.md`, `coding-guide.md` and `test-plan.md`. Re-verify exact protected-base paths before any G2 write.
