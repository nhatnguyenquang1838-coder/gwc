# Coding guide

- Preserve the provider-neutral in-memory boundary in
  `tools/node_architect/durable_checkpoint_runtime.py`.
- Preserve the scenario-matrix and typed outcome model in
  `tools/node_architect/crash_replay_harness.py`.
- Treat unknown external outcomes as unresolved until readback; never blind
  retry an idempotent side effect.
- Use the existing focused test modules and add assertions at the smallest
  existing seam. Do not modify `.gwc` authority semantics or production paths.
