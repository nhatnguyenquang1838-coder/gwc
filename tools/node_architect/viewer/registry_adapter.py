#!/usr/bin/env python3
"""Data-only Cytoscape v3 adapter for the canonical runtime registries.

The repository does not own a Cytoscape runtime. This module supplies the
external-data binding contract used by a v3 renderer: every registry node is
retained, inactive nodes receive an ``inactive`` class, and visual scaffold
edges are never promoted to executable runtime dependencies.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
from typing import Any, Iterable


REGISTRY_FILES = {
    "nodes": "core/node-architect/node-registry.json",
    "scenarios": "core/node-architect/scenario-registry.json",
    "profiles": "core/node-architect/profile-registry.json",
    "graph": "core/node-architect/runtime-graph-registry.json",
}


def load_registry_bundle(root: Path) -> dict[str, Any]:
    """Load the external registry data used by the v3 view."""

    bundle: dict[str, Any] = {}
    for name, relative in REGISTRY_FILES.items():
        with (root / relative).open("r", encoding="utf-8") as handle:
            bundle[name] = json.load(handle)
    return bundle


def _edge_classes(edge: dict[str, Any]) -> list[str]:
    edge_type = edge["edge_type"]
    classes = [edge_type]
    if edge_type in {"visualization", "suggested_sequence", "audit"}:
        classes.append("visual-only")
    if edge["runtime_executable"]:
        classes.append("runtime-executable")
    return classes


def build_cytoscape_elements(
    bundle: dict[str, Any],
    active_node_ids: Iterable[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Build Cytoscape-compatible node and edge elements without filtering."""

    active = set(active_node_ids or ())
    nodes = []
    for node in bundle["nodes"]["nodes"]:
        node_id = node["id"]
        classes = ["runtime-node"]
        classes.append("active" if not active or node_id in active else "inactive")
        nodes.append(
            {
                "data": {
                    "id": node_id,
                    "label": node_id,
                    "family": node["family"],
                    "maturity": node["maturity"],
                    "source_status": node["source_status"],
                    "provenance": node["provenance"],
                },
                "classes": " ".join(classes),
            }
        )

    edges = []
    for index, edge in enumerate(bundle["graph"]["edges"]):
        edges.append(
            {
                "data": {
                    "id": f"edge-{index}",
                    "source": edge["source"],
                    "target": edge["target"],
                    "edge_type": edge["edge_type"],
                    "runtime_executable": edge["runtime_executable"],
                    "provenance": edge["provenance"],
                },
                "classes": " ".join(_edge_classes(edge)),
            }
        )
    return {"nodes": nodes, "edges": edges}


def enumerate_routes_to_green(
    bundle: dict[str, Any],
    start_node_ids: Iterable[str],
    green_targets: Iterable[str],
    max_routes: int = 256,
) -> list[list[str]]:
    """Enumerate bounded simple routes using runtime edges only."""

    green = set(green_targets)
    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in bundle["graph"]["edges"]:
        if edge["runtime_executable"] and edge["edge_type"] in {"runtime", "dependency"}:
            adjacency[edge["source"]].append(edge["target"])

    routes: list[list[str]] = []

    def visit(path: list[str]) -> None:
        if len(routes) >= max_routes:
            return
        current = path[-1]
        if current in green:
            routes.append(path.copy())
            return
        for target in adjacency.get(current, []):
            if target not in path:
                visit(path + [target])

    for start in start_node_ids:
        visit([start])
    return routes


def classify_route(
    route: list[str],
    green_targets: Iterable[str],
    human_boundaries: Iterable[str] = (),
) -> str:
    """Classify a route without treating visual edges as runtime evidence."""

    if any(boundary in route for boundary in human_boundaries):
        return "HUMAN_REQUIRED"
    if route and route[-1] in set(green_targets):
        return "VALID_AUTO"
    return "CONDITIONAL"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--active-node", action="append", default=[])
    args = parser.parse_args(argv)
    bundle = load_registry_bundle(args.root.resolve())
    elements = build_cytoscape_elements(bundle, args.active_node or None)
    print(json.dumps(elements, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
