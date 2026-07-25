# SCRUM-102 鈥?Design canonical node, scenario, profile and history schemas

## Objective

Define typed versioned contracts for runtime nodes, scenarios, profiles, guard expressions, graphs, revisions and history.

## Delivery wave

Wave 1

## Dependencies

- Requires: None
- Parallel with: SCRUM-100, SCRUM-101

## Scope

### Included

- Node contract metadata dimensions
- Scenario activation and route model
- Profile overlays
- Typed guards
- Runtime graph/revision/history
- Promotion lifecycle metadata

### Excluded

- Graph compiler implementation
- Durable engine
- Automatic catalog promotion

## Definition of done

- Schemas are versioned and additionalProperties policy is explicit.
- No graph edge is executable without provenance/type/rule.
- Node promotion checklist is machine-checkable.

## Handoff

Read `task.yaml` first, then `implementation-plan.md`, `coding-guide.md` and `test-plan.md`. Re-verify exact protected-base paths before any G2 write.

