# Run Impact Analysis

## Executive finding

The protected base already contains a mature governance contract surface, but the executable runtime is uneven. The highest-risk gap is not the absence of an adaptive compiler; it is the mismatch between declared authority/lifecycle behavior and the current executable state/registry surfaces.

## Direct impact

- `core/task-lifecycle/gate-transition-map.yaml`: current terminal path reaches `completed` directly after validation and does not explicitly model merge/post-merge verification states.
- `tools/validate_g01.py`: plan handoff and exact-plan read enforcement exist and must remain compatible.
- `projects/gwc/*`: project authority and automatic bounded-work policy must remain source-of-truth.
- `tools/node_architect/*` and `schemas/node-architect/*`: focused catalog projection must evolve without presenting proposed nodes as canonical.
- Cytoscape v3: must consume external registries rather than hard-coded node/scenario arrays.

## Transitive impact

- Existing task-scoped G0-G3 artifacts and validators.
- Power distribution manifest/checksum generation.
- Consumer projects using generated governance packages.
- Jira state/projection integration.
- G5 exact-SHA evidence and continuation behavior.
- Future UA, Task-Me and BMAD adapter contracts.

## Risk

- **R2 overall** for planning/schema work.
- Escalate to **R3** if changes rewrite authority semantics, protected-base transition behavior, security boundaries, release workflows, or consumer compatibility.
- No production data, credentials, deployment or merge action is in scope.

## Recommended delivery

Run three knowledge lanes in parallel, converge on blocker resolution, then build registries and v3 binding. Do not start the durable runtime or graph compiler in this PR.

