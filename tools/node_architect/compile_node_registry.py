#!/usr/bin/env python3
"""Compile GWC runtime node JSON files into a deterministic node registry.

This tool is intentionally stdlib-only so it can run in local-agent and CI
contexts without adding dependencies. It does not replace full JSON Schema
validation; it performs the minimum structural checks needed before the
registry can be passed to validate_node_registry.py.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


NODE_FILE_SUFFIX = ".node.json"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected JSON object")
    return data


def _iter_node_files(input_dir: Path) -> list[Path]:
    if not input_dir.exists() or not input_dir.is_dir():
        raise ValueError(f"{input_dir}: input directory does not exist")

    return sorted(path for path in input_dir.rglob(f"*{NODE_FILE_SUFFIX}") if path.is_file())


def _normalize_node(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    required = ("node_id", "node_type", "title", "canonical", "authority_boundary", "gates")
    missing = [field for field in required if field not in data]
    if missing:
        raise ValueError(f"{path}: missing required fields: {', '.join(missing)}")

    gates = data["gates"]
    if not isinstance(gates, list):
        raise ValueError(f"{path}: gates must be a list")

    node = {key: data[key] for key in sorted(data) if key != "edges"}
    node["gates"] = sorted(gates)
    return node


def compile_registry(input_dir: Path, registry_id: str) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []

    node_files = _iter_node_files(input_dir)
    if not node_files:
        raise ValueError(f"{input_dir}: no *{NODE_FILE_SUFFIX} files found")

    for path in node_files:
        data = _load_json(path)
        nodes.append(_normalize_node(path, data))

        raw_edges = data.get("edges", [])
        if not isinstance(raw_edges, list):
            raise ValueError(f"{path}: edges must be a list when provided")
        for edge in raw_edges:
            if not isinstance(edge, dict):
                raise ValueError(f"{path}: edge must be an object")
            edges.append({key: edge[key] for key in sorted(edge)})

    nodes.sort(key=lambda item: item["node_id"])
    edges.sort(key=lambda item: (item.get("source", ""), item.get("target", ""), item.get("relation", "")))

    return {"schema_version": "0.1", "registry_id": registry_id, "nodes": nodes, "edges": edges}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, separators=(",", ": ")) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--registry-id", default="gwc-node-registry")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        registry = compile_registry(args.input_dir, args.registry_id)
        _write_json(args.output, registry)
    except ValueError as exc:
        print(json.dumps({"outcome": "FAIL", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1

    print(json.dumps({"outcome": "PASS", "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
