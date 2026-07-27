#!/usr/bin/env python3
"""Data-only Cytoscape v3 adapter for canonical registries and history."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from tools.node_architect.viewer.run_history_adapter import (
    build_run_history_elements,
    overlay_run_history,
)

REGISTRY_FILES = {
    "nodes": "core/node-architect/node-registry.json",
    "scenarios": "core/node-architect/scenario-registry.json",
    "profiles": "core/node-architect/profile-registry.json",
    "graph": "core/node-architect/runtime-graph-registry.json",
}


def load_registry_bundle(root: Path) -> dict[str, Any]:
    bundle: dict[str, Any] = {}
    for name, relative in REGISTRY_FILES.items():
        with (root / relative).open("r", encoding="utf-8") as handle:
            bundle[name] = json.load(handle)
    return bundle


def _edge_classes(edge: Mapping[str, Any]) -> list[str]:
    edge_type = str(edge["edge_type"])
    classes = [edge_type]
    if edge_type in {
        "visualization",
        "suggested_sequence",
        "audit",
        "human_authority",
        "blocked",
        "scenario-route-history",
        "scenario-route-node",
    }:
        classes.append("visual-only")
    if edge["runtime_executable"]:
        classes.append("runtime-executable")
    return classes


def build_scenario_decision_elements(
    decision: Mapping[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    """Convert one immutable scenario decision into projection-only elements."""
    decision_id = str(decision.get("decision_id") or decision.get("decision_digest") or "")
    scenario_id = str(decision.get("scenario_id") or "")
    if not decision_id:
        raise ValueError("scenario decision_id is required")
    if not scenario_id:
        raise ValueError("scenario scenario_id is required")

    scenario_node_id = f"scenario:{scenario_id}"
    nodes = [
        {
            "data": {
                "id": scenario_node_id,
                "kind": "scenario",
                "scenario_id": scenario_id,
                "scenario_version": decision.get("scenario_version"),
                "classification": decision.get("classification"),
                "decision_id": decision_id,
                "graph_revision": decision.get("graph_revision"),
                "facts_digest": decision.get("facts_digest"),
                "provenance": "scenario-decision-history",
            },
            "classes": (
                "scenario-decision "
                + str(decision.get("classification") or "unknown").lower()
            ),
        }
    ]
    edges: list[dict[str, Any]] = []
    selected = decision.get("selected_route") or {}
    selected_path = selected.get("path")

    for route in decision.get("candidate_routes") or []:
        rank = route.get("rank")
        route_node_id = f"route:{decision_id}:{rank}"
        is_selected = route.get("path") == selected_path and selected_path is not None
        nodes.append(
            {
                "data": {
                    "id": route_node_id,
                    "kind": "candidate-route",
                    "decision_id": decision_id,
                    "rank": rank,
                    "classification": route.get("class"),
                    "path": route.get("path", []),
                    "selected": is_selected,
                    "provenance": "scenario-decision-history",
                },
                "classes": (
                    ("selected-route" if is_selected else "candidate-route")
                    + " "
                    + str(route.get("class") or "unknown").lower()
                ),
            }
        )
        edges.append(
            {
                "data": {
                    "id": f"scenario-route:{decision_id}:{rank}",
                    "source": scenario_node_id,
                    "target": route_node_id,
                    "edge_type": "scenario-route-history",
                    "runtime_executable": False,
                    "provenance": "scenario-decision-history",
                },
                "classes": "scenario-route-history visual-only",
            }
        )
        for index, runtime_node_id in enumerate(route.get("path", [])):
            edges.append(
                {
                    "data": {
                        "id": f"route-node:{decision_id}:{rank}:{index}",
                        "source": route_node_id,
                        "target": str(runtime_node_id),
                        "edge_type": "scenario-route-node",
                        "runtime_executable": False,
                        "provenance": "scenario-decision-history",
                    },
                    "classes": "scenario-route-node visual-only",
                }
            )
    return {"nodes": nodes, "edges": edges}


def build_cytoscape_elements(
    bundle: Mapping[str, Any],
    active_node_ids: Iterable[str] | None = None,
    run_history: Mapping[str, Any] | None = None,
    scenario_decision: Mapping[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Build the registry graph and optionally overlay durable histories."""
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

    elements: dict[str, list[dict[str, Any]]] = {"nodes": nodes, "edges": edges}
    if run_history is not None:
        elements = overlay_run_history(elements, build_run_history_elements(run_history))
    if scenario_decision is not None:
        elements = overlay_run_history(
            elements,
            build_scenario_decision_elements(scenario_decision),
        )
    return elements


def enumerate_routes_to_green(
    bundle: Mapping[str, Any],
    start_node_ids: Iterable[str],
    green_targets: Iterable[str],
    max_routes: int = 256,
) -> list[list[str]]:
    green = set(green_targets)
    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in bundle["graph"]["edges"]:
        if edge["runtime_executable"] and edge["edge_type"] in {"runtime", "dependency"}:
            adjacency[edge["source"]].append(edge["target"])
    for targets in adjacency.values():
        targets.sort()

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

    for start in sorted(str(item) for item in start_node_ids):
        visit([start])
    return routes


def classify_route(
    route: list[str],
    green_targets: Iterable[str],
    human_boundaries: Iterable[str] = (),
) -> str:
    if any(boundary in route for boundary in human_boundaries):
        return "HUMAN_REQUIRED"
    if route and route[-1] in set(green_targets):
        return "VALID_AUTO"
    return "CONDITIONAL"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[3],
    )
    parser.add_argument("--active-node", action="append", default=[])
    parser.add_argument("--run-history", type=Path)
    parser.add_argument("--scenario-decision", type=Path)
    args = parser.parse_args(argv)

    bundle = load_registry_bundle(args.root.resolve())
    run_history = None
    if args.run_history:
        run_history = json.loads(args.run_history.read_text(encoding="utf-8"))
    scenario_decision = None
    if args.scenario_decision:
        scenario_decision = json.loads(args.scenario_decision.read_text(encoding="utf-8"))

    elements = build_cytoscape_elements(
        bundle,
        args.active_node or None,
        run_history,
        scenario_decision,
    )
    print(json.dumps(elements, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
