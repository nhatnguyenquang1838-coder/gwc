#!/usr/bin/env python3
"""Validate GWC reference nodes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REFERENCE_DIR = Path("core/node-architect/reference-nodes")
REQUIRED_CLASSES = {"read_only", "side_effect_write", "suspend_resume"}


def load_nodes(root: Path) -> list[dict]:
    directory = root / REFERENCE_DIR
    if not directory.exists():
        return []
    nodes = []
    for path in sorted(directory.glob("*.node.json")):
        with path.open("r", encoding="utf-8") as handle:
            node = json.load(handle)
        node["__path"] = str(path.relative_to(root))
        nodes.append(node)
    return nodes


def require_key(node: dict, key: str, errors: list[str]) -> None:
    if key not in node:
        errors.append(f"{node.get('__path', '<unknown>')}: missing {key}")


def validate_node(node: dict) -> list[str]:
    errors: list[str] = []
    for key in ("schema_version", "node_id", "node_version", "node_class", "entry", "do", "branches", "exit", "next"):
        require_key(node, key, errors)
    if errors:
        return errors

    node_class = node["node_class"]
    do_block = node["do"]
    if node_class == "read_only" and do_block.get("side_effect") is not False:
        errors.append(f"{node['__path']}: read_only node must declare side_effect=false")
    if node_class == "side_effect_write":
        if do_block.get("side_effect") is not True:
            errors.append(f"{node['__path']}: side_effect_write node must declare side_effect=true")
        if do_block.get("idempotency_key_required") is not True:
            errors.append(f"{node['__path']}: side_effect_write node must require idempotency key")
        if not do_block.get("readback_node"):
            errors.append(f"{node['__path']}: side_effect_write node must declare readback_node")
    if node_class == "suspend_resume":
        if do_block.get("checkpoint_before_suspend") is not True:
            errors.append(f"{node['__path']}: suspend_resume node must checkpoint before suspend")
        if not do_block.get("resume_signal"):
            errors.append(f"{node['__path']}: suspend_resume node must declare resume_signal")
    if not isinstance(node.get("branches"), list) or not node["branches"]:
        errors.append(f"{node['__path']}: branches must be non-empty")
    if not isinstance(node.get("next"), list) or not node["next"]:
        errors.append(f"{node['__path']}: next must be non-empty")
    return errors


def validate_nodes(nodes: list[dict]) -> list[str]:
    errors: list[str] = []
    classes = {node.get("node_class") for node in nodes}
    if classes != REQUIRED_CLASSES:
        errors.append(f"expected exactly reference classes {sorted(REQUIRED_CLASSES)}, got {sorted(classes)}")
    node_ids = [node.get("node_id") for node in nodes]
    if len(set(node_ids)) != len(node_ids):
        errors.append("node_id values must be unique")
    for node in nodes:
        errors.extend(validate_node(node))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    nodes = load_nodes(root)
    errors = []
    if len(nodes) != 3:
        errors.append(f"expected exactly 3 reference nodes, got {len(nodes)}")
    errors.extend(validate_nodes(nodes))

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Validated 3 reference nodes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
