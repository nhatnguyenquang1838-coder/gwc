#!/usr/bin/env python3
"""Validate the runtime_checkpoint controlled node catalog batch.

This validator is intentionally stdlib-only so it can run in minimal
governance workspaces without installing JSON Schema dependencies.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

EXPECTED_FAMILY = "runtime_checkpoint"
EXPECTED_NODE_COUNT = 9
EXPECTED_AUTHORITY = "g2_required"
EXPECTED_GATES = {"G2_EXECUTION"}
ALLOWED_KEYS = {
    "node_id",
    "node_type",
    "title",
    "description",
    "canonical",
    "authority_boundary",
    "gates",
}
ALLOWED_NODE_TYPES = {"actor", "workflow", "gate", "tool", "schema", "state", "projection", "connector"}
ALLOWED_CANONICAL = {"canonical", "delivery_evidence", "audit_projection", "resume_hint"}


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise AssertionError(f"{path}: expected object")
    return value


def iter_node_files(family_dir: Path) -> Iterable[Path]:
    return sorted(family_dir.glob("*.node.json"))


def validate_family(family_dir: Path) -> None:
    if not family_dir.exists():
        raise AssertionError(f"missing family dir: {family_dir}")

    readme = family_dir / "README.md"
    if not readme.exists():
        raise AssertionError("missing README.md")

    node_files = list(iter_node_files(family_dir))
    if len(node_files) != EXPECTED_NODE_COUNT:
        raise AssertionError(f"expected {EXPECTED_NODE_COUNT} nodes, found {len(node_files)}")

    seen: set[str] = set()
    for path in node_files:
        node = load_json(path)

        extra = sorted(set(node) - ALLOWED_KEYS)
        if extra:
            raise AssertionError(f"{path.name}: unexpected keys: {extra}")

        missing = sorted(ALLOWED_KEYS - set(node))
        if missing:
            raise AssertionError(f"{path.name}: missing keys: {missing}")

        node_id = node["node_id"]
        if not isinstance(node_id, str) or not node_id.startswith(EXPECTED_FAMILY + "."):
            raise AssertionError(f"{path.name}: invalid node_id {node_id!r}")
        if node_id in seen:
            raise AssertionError(f"duplicate node_id: {node_id}")
        seen.add(node_id)

        expected_filename = node_id.split(".", 1)[1] + ".node.json"
        if path.name != expected_filename:
            raise AssertionError(f"{path.name}: filename must match node id suffix {expected_filename}")

        if node["node_type"] not in ALLOWED_NODE_TYPES:
            raise AssertionError(f"{path.name}: invalid node_type {node['node_type']!r}")

        if not isinstance(node["title"], str) or not node["title"].strip():
            raise AssertionError(f"{path.name}: title must be non-empty")

        if not isinstance(node["description"], str) or not node["description"].strip():
            raise AssertionError(f"{path.name}: description must be non-empty")

        if node["canonical"] not in ALLOWED_CANONICAL:
            raise AssertionError(f"{path.name}: invalid canonical {node['canonical']!r}")

        if node["authority_boundary"] != EXPECTED_AUTHORITY:
            raise AssertionError(
                f"{path.name}: authority_boundary must be {EXPECTED_AUTHORITY}, got {node['authority_boundary']!r}"
            )

        gates = node["gates"]
        if not isinstance(gates, list) or not gates:
            raise AssertionError(f"{path.name}: gates must be a non-empty list")
        if len(gates) != len(set(gates)):
            raise AssertionError(f"{path.name}: gates must be unique")
        if set(gates) != EXPECTED_GATES:
            raise AssertionError(f"{path.name}: gates must be exactly {sorted(EXPECTED_GATES)}, got {gates!r}")

    readme_text = readme.read_text(encoding="utf-8")
    for required in [
        "batch-04-runtime-checkpoint",
        "runtime_checkpoint",
        "G2_EXECUTION",
        "no runtime engine implementation",
        "no production data access",
    ]:
        if required not in readme_text:
            raise AssertionError(f"README.md missing required text: {required}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--family-dir",
        default="core/node-architect/node-catalog/runtime_checkpoint",
        help="Path to runtime_checkpoint family directory",
    )
    args = parser.parse_args()
    validate_family(Path(args.family_dir))
    print("PASS runtime_checkpoint node catalog")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
