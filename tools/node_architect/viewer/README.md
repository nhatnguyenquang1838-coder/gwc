# Cytoscape v3 registry adapter

`registry_adapter.py` is the renderer-neutral data boundary for the v3 full-flow
view. It loads node, scenario, profile and graph JSON from the canonical
registries and emits Cytoscape-compatible elements.

The adapter deliberately keeps all 81 nodes in the element set. A selected
route or active-node set changes classes only; it does not delete inactive
nodes. Runtime edges are executable only when the registry marks them as
`runtime` or `dependency`. Visualization and suggested-sequence scaffold
edges are retained for context and marked `visual-only`.
