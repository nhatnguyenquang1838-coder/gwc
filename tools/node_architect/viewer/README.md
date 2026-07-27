# Cytoscape v3 registry and run-history adapters

`registry_adapter.py` is the renderer-neutral data boundary for the v3 full-flow view. It retains every canonical registry node. Active routes change CSS classes only; visual scaffold edges never become executable runtime dependencies.

SCRUM-110 adds `run_history_adapter.py`, which consumes real durable run, event, and checkpoint records and emits Cytoscape-compatible history nodes and visual-only history edges. Exact task, repository, SHA, scope, graph revision, event sequence, checkpoint revision, lease owner, and fencing token remain visible in element data.

Use:

```bash
python tools/node_architect/viewer/registry_adapter.py \
  --root . \
  --run-history /path/to/durable-run-history.json
```

The history overlay marks observed canonical nodes with `history-observed`. History edges are always `runtime_executable: false`; they visualize evidence and never grant execution authority.
