feat(gwc): SCRUM-356 NA81-F7 governance-tree-build topology + canonical order + provenance

Implement the missing SCRUM-356 (NA81-F7-N05) node-architect maturity gap on top
of the existing `package_export.governance-tree-build` builder (SCRUM-233).
The SCRUM-233 builder only copied files flat; it lacked the explicit SCRUM-356
requirements (DELTA_REQUIRED):

- `PlanEntry` gains `parent` (instruction-tree parent target) and `order`
  (sibling ordering key); entries without a parent are roots.
- Pre-build topology validation (in-memory, before any staging write) blocks:
  * `TREE_DUPLICATE_ENTRY` — two entries share the same (source, target).
  * `TREE_MISSING_PARENT` — an entry references a parent not in the plan.
  * `TREE_CYCLE_DETECTED` — the parent graph contains a cycle (DFS colouring).
  * `TREE_AMBIGUOUS_ORDER` — two siblings share an explicit `order`.
- Canonical ordering: entries are copied in topological order (parents before
  children), siblings ordered by `order` then target — fully deterministic.
- Per-entry provenance: each completion-evidence inventory row now carries
  `parent`, `order`, `depth` (root distance), `tree_path` (root -> node path)
  and `index` (canonical position). `compute_plan_digest` / `compute_tree_digest`
  are topology-aware.
- Fail-closed and backward compatible: legacy flat plans (no parent / no order)
  keep the prior behaviour and digest semantics.

Wiring:
- New `TREE_*` reason codes added to the closed taxonomy and routed in
  `export_failure_routing.py` (cycle -> HUMAN_REQUIRED; duplicate/missing-parent/
  ambiguous-order -> REPAIR_INPUT), mirrored in the routing test table.
- `governance-tree-build.schema.json` `reason` enum and `entry_inventory`
  extended with the new provenance fields (closed schema preserved).

No `*.node.json` `description`/`source` fields edited (provenance trap avoided).

Parent authority: AR-SCRUM288-RECERT-20260814-R10 (issue #232), task SCRUM-356.
Targets pre-prod only; main is FORBIDDEN.
