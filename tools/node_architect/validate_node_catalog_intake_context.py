#!/usr/bin/env python3
"""Validate the REVAMP-GWC-016 intake_context node family."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

EXPECTED_FAMILY = "intake_context"
EXPECTED_COUNT = 9
EXPECTED_GATE = "G0_CONTEXT"
ALLOWED_AUTHORITY = {"read_only", "none"}
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
REQUIRED_KEYS = {
    "node_id",
    "node_type",
    "title",
    "canonical",
    "authority_boundary",
    "gates",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_family_dir() -> Path:
    return _repo_root() / "core" / "node-architect" / "node-catalog" / EXPECTED_FAMILY


def _load_node(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: node file must contain a JSON object")
    return data


def _validate_node(path: Path, node: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    extra = sorted(set(node) - (REQUIRED_KEYS | {"description"}))
    missing = sorted(REQUIRED_KEYS - set(node))
    if missing:
        errors.append(f"{path}: missing required keys: {', '.join(missing)}")
    if extra:
        errors.append(f"{path}: unexpected keys: {', '.join(extra)}")

    node_id = node.get("node_id")
    if not isinstance(node_id, str) or not node_id.startswith(f"{EXPECTED_FAMILY}."):
        errors.append(f"{path}: node_id must start with {EXPECTED_FAMILY}.")

    node_type = node.get("node_type")
    if node_type not in ALLOWED_NODE_TYPES:
        errors.append(f"{path}: invalid node_type {node_type!r}")

    canonical = node.get("canonical")
    if canonical not in ALLOWED_CANONICAL:
        errors.append(f"{path}: invalid canonical {canonical!r}")

    title = node.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append(f"{path}: title must be a non-empty string")

    authority = node.get("authority_boundary")
    if authority not in ALLOWED_AUTHORITY:
        errors.append(
            f"{path}: intake_context nodes must be read-only/none authority, got {authority!r}"
        )

    gates = node.get("gates")
    if gates != [EXPECTED_GATE]:
        errors.append(f"{path}: gates must be exactly [{EXPECTED_GATE!r}]")

    description = node.get("description")
    if description is not None and not isinstance(description, str):
        errors.append(f"{path}: description must be a string when present")

    return errors


def validate_family(family_dir: Path) -> list[str]:
    errors: list[str] = []
    files = sorted(family_dir.glob("*.node.json"))

    if len(files) != EXPECTED_COUNT:
        errors.append(
            f"{family_dir}: expected exactly {EXPECTED_COUNT} .node.json files, found {len(files)}"
        )

    seen_ids: set[str] = set()
    for path in files:
        try:
            node = _load_node(path)
        except Exception as exc:  # noqa: BLE001 - CLI validator should report all file failures.
            errors.append(f"{path}: failed to load JSON: {exc}")
            continue

        node_id = node.get("node_id")
        if isinstance(node_id, str):
            if node_id in seen_ids:
                errors.append(f"{path}: duplicate node_id {node_id}")
            seen_ids.add(node_id)

        errors.extend(_validate_node(path, node))

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--family-dir",
        type=Path,
        default=_default_family_dir(),
        help="Path to intake_context node family directory.",
    )
    args = parser.parse_args()

    errors = validate_family(args.family_dir)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print(f"PASS: {EXPECTED_FAMILY} node family has {EXPECTED_COUNT} valid nodes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
