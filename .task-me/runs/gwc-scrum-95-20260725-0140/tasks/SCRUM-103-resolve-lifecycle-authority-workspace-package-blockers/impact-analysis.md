# Impact Analysis — SCRUM-103

## Direct surfaces

- `core/task-lifecycle/gate-transition-map.yaml`
- `core/GATE_LIFECYCLE_CONTRACT_v1.0.md`
- `tools/validate_g01.py`
- `projects/gwc/project-instructions.md`
- `distribution/power-package.yaml`
- `.github/workflows/validate-instructions.yml`

## Impact classes

- Contract: yes
- Runtime: yes
- Test: tests must be added
- Operational: validation and consumer-package compatibility
- Data/production: out of scope

## Risk

- Class: `R2`
- Main risk: changes may weaken authority or present proposed registry content as canonical.
- Mitigation: exact-base diff review, negative tests, schema fixtures and G3 independent review.
