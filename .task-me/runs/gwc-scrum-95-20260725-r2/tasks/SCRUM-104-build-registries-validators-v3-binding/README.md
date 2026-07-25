# SCRUM-104 鈥?Build canonical registries, validators and v3 data binding

## Objective

Materialize approved registry entries and connect the full-flow v3 visualization to external registry/scenario data.

## Delivery wave

Wave 3

## Dependencies

- Requires: SCRUM-100, SCRUM-101, SCRUM-102, SCRUM-103
- Parallel with: None

## Scope

### Included

- 81-slot node registry with maturity/provenance
- Initial canonical scenario registry
- Flow profile registry
- Registry validators
- External data contract for v3
- Visual versus runtime edge separation

### Excluded

- Executing runtime nodes
- Self-improvement
- Automatic graph mutation

## Definition of done

- All 81 slots have explicit maturity and provenance.
- Registry/schema validation runs in CI.
- V3 uses external data rather than hard-coded scenario arrays.
- Phase 2 can select three pilot nodes from the registry.

## Handoff

Read `task.yaml` first, then `implementation-plan.md`, `coding-guide.md` and `test-plan.md`. Re-verify exact protected-base paths before any G2 write.

