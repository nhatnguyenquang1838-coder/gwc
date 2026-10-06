# Impact Analysis 鈥?SCRUM-100

## Direct surfaces

- `AGENTS.md`
- `projects/gwc/project-profile.yaml`
- `projects/gwc/project-instructions.md`
- `projects/gwc/project-extension.md`
- `core/task-lifecycle/gate-transition-map.yaml`
- `tools/validate_g01.py`
- `tests/test_g1_implementation_plan_handoff.py`
- `tools/node_architect/project_runtime_knowledge_graph.py`
- `tests/test_runtime_catalog_taxonomy_kg.py`

## Impact classes

- Contract: yes
- Runtime: yes
- Test: yes
- Operational: validation and consumer-package compatibility
- Data/production: out of scope

## Risk

- Class: `R1`
- Main risk: changes may weaken authority or present proposed registry content as canonical.
- Mitigation: exact-base diff review, negative tests, schema fixtures and G3 independent review.

