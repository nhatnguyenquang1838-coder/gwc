#!/usr/bin/env python3
"""Validate the gate_authority node catalog family.

This validator is intentionally stdlib-only so it can run in lightweight
governance CI without installing third-party packages.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EXPECTED_FAMILY = "gate_authority"
EXPECTED_COUNT = 9
ALLOWED_GATES = {"G1_ALIGNMENT", "G2_EXECUTION"}
EXPECTED_AUTHORITY = "g2_required"
REQUIRED_FIELDS = {
    "node_id",
    "node_type",
    "title",
    "canonical",
    "authority_boundary",
    "gates",
}
ALLOWED_NODE_TYPES = {
    "actor",
    "workflow",
    "gate",
    "tool",
    "schema",
    "state",
    "projection",
    "connector",
}
ALLOWED_CANONICAL = {
    "canonical",
    "delivery_evidence",
    "audit_projection",
    "resume_hint",
}
ALLOWED_KEYS = REQUIRED_FIELDS | {"description"}


def load_node(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON: {exc}") from exc


def validate_node(path: Path, node: dict) -> list[str]:
    errors: list[str] = []

    extra = set(node) - ALLOWED_KEYS
    missing = REQUIRED_FIELDS - set(node)
    if extra:
        errors.append(f"{path}: unexpected fields: {sorted(extra)}")
    if missing:
        errors.append(f"{path}: missing fields: {sorted(missing)}")

    node_id = node.get("node_id")
    if not isinstance(node_id, str) or not node_id.startswith(f"{EXPECTED_FAMILY}."):
        errors.append(f"{path}: node_id must start with {EXPECTED_FAMILY}.")

    node_type = node.get("node_type")
    if node_type not in ALLOWED_NODE_TYPES:
        errors.append(f"{path}: invalid node_type {node_type!r}")

    canonical = node.get("canonical")
    if canonical not in ALLOWED_CANONICAL:
        errors.append(f"{path}: invalid canonical {canonical!r}")

    authority = node.get("authority_boundary")
    if authority != EXPECTED_AUTHORITY:
        errors.append(f"{path}: authority_boundary must be {EXPECTED_AUTHORITY}")

    gates = node.get("gates")
    if not isinstance(gates, list) or not gates:
        errors.append(f"{path}: gates must be a non-empty list")
    else:
        gate_set = set(gates)
        if len(gate_set) != len(gates):
            errors.append(f"{path}: gates must be unique")
        if not gate_set.issubset(ALLOWED_GATES):
            errors.append(f"{path}: gates must stay within {sorted(ALLOWED_GATES)}")

    if not isinstance(node.get("title"), str) or not node["title"].strip():
        errors.append(f"{path}: title must be non-empty")

    return errors


def validate_family(family_dir: Path) -> list[str]:
    errors: list[str] = []

    if family_dir.name != EXPECTED_FAMILY:
        errors.append(f"family directory must be named {EXPECTED_FAMILY}")

    node_files = sorted(family_dir.glob("*.node.json"))
    if len(node_files) != EXPECTED_COUNT:
        errors.append(
            f"expected exactly {EXPECTED_COUNT} node files, found {len(node_files)}"
        )

    seen_ids: set[str] = set()
    for path in node_files:
        node = load_node(path)
        node_id = node.get("node_id")
        if isinstance(node_id, str):
            if node_id in seen_ids:
                errors.append(f"{path}: duplicate node_id {node_id}")
            seen_ids.add(node_id)
        errors.extend(validate_node(path, node))

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--family-dir", required=True)
    args = parser.parse_args(argv)

    family_dir = Path(args.family_dir)
    errors = validate_family(family_dir)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print("GATE_AUTHORITY_NODE_FAMILY_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
