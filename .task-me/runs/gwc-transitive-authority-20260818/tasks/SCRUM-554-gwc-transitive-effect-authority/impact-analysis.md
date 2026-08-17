# Impact analysis

## Direct surfaces
- `schemas/gate-action-authority.schema.json`
- `tools/validate_gate_action.py`
- `core/GATE_LIFECYCLE_CONTRACT_v1.0.md`
- `core/task-lifecycle/gate-transition-map.yaml`
- `tests/`

## Transitive impact
- Controller/governance decisions can trigger GitHub Actions, bots, release/archive retention, deployment providers, cross-repository writes, or production-capable integrations.
- The implementation must model deterministic downstream effects before the parent mutation executes.
- A child effect in another repository is a separate authority lane.

## Risk
- Risk class: **R2** because the change affects governance/control-plane decisions.
- Primary failure mode: false PASS broadens authority or attaches valid evidence to the wrong execution identity.
- Compatibility risk: new semantics must not silently invalidate existing valid direct-action flows when no unauthorized child effect exists.
