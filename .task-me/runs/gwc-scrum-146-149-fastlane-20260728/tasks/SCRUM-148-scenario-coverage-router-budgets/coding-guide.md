# Coding guide

- Use `evaluate_guard`, `enumerate_routes`, `decide_scenario`, and
  `append_scenario_decision` in `tools/p3_backward_graph.py`; do not create a
  second router.
- Keep scenario provenance and materialized-count checks in
  `tools/node_architect/validate_runtime_registry.py`.
- Preserve deterministic ordering and strict type comparison.
- Make every budget failure typed and non-auto-executable. Keep projection and
  history edges explicitly `runtime_executable: false`.
