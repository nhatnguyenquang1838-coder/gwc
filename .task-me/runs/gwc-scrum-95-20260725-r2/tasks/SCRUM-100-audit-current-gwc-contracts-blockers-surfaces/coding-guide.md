# Coding Guide 鈥?SCRUM-100

## Verified paths

- `AGENTS.md`
- `projects/gwc/project-profile.yaml`
- `projects/gwc/project-instructions.md`
- `projects/gwc/project-extension.md`
- `core/task-lifecycle/gate-transition-map.yaml`
- `tools/validate_g01.py`
- `tests/test_g1_implementation_plan_handoff.py`
- `tools/node_architect/project_runtime_knowledge_graph.py`
- `tests/test_runtime_catalog_taxonomy_kg.py`

## Required approach

1. Re-read every target file from the exact protected base.
2. Locate and extend the current mechanism.
3. Add failing tests before behavior-changing edits.
4. Keep authority and evidence binding explicit.
5. Reject silent compatibility breaks.
6. Review the full diff for generated noise and scope drift.

## Prohibited changes

- No direct write to `main`.
- No merge, release, deployment or production operation.
- No weakening of G0-G6 authority.
- No free-form LLM text as executable guard or policy.
- No opportunistic refactor outside the Jira task.

