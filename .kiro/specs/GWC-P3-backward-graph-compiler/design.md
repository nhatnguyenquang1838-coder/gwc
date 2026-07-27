# Design — SCRUM-97 P3 Contract-First Split

P3 compiles from desired/safe-failure outcomes backward through capabilities and evidence dependencies. NetworkX-style DiGraph semantics map to predecessors, successors, topological ordering, cycle detection and bounded path enumeration. Cytoscape.js binding uses element JSON with nodes and edges under data.id/source/target/label. Visual edges remain projection only and never grant runtime authority.

Route classes are VALID_AUTO, VALID_HUMAN, CONDITIONAL, BLOCKED and UNSAFE. Any human authority boundary stops auto-execution.
