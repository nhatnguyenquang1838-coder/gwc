#!/usr/bin/env python3
"""Validate the repo_delivery node catalog batch."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

EXPECTED_NODES = {
    "repo_delivery.branch-creation",
    "repo_delivery.base-drift-check",
    "repo_delivery.scoped-file-write",
    "repo_delivery.diff-readback",
    "repo_delivery.draft-pr-creation",
    "repo_delivery.ci-run-capture",
    "repo_delivery.ci-failure-repair",
    "repo_delivery.ready-for-review-promotion",
    "repo_delivery.pr-blocker-check",
}
ALLOWED_KEYS = {
    "node_id",
    "node_type",
    "title",
    "canonical",
    "authority_boundary",
    "gates",
    "description",
}
ALLOWED_NODE_TYPES = {"actor", "workflow", "gate", "tool", "schema", "state", "projection", "connector"}
ALLOWED_CANONICAL = {"canonical", "delivery_evidence", "audit_projection", "resume_hint"}
ALLOWED_GATES = {"G2_EXECUTION", "G3_PR"}


def validate_family(family_dir: Path) -> list[str]:
    errors: list[str] = []
    files = sorted(family_dir.glob("*.node.json"))
    if len(files) != 9:
        errors.append(f"expected 9 node files, found {len(files)}")

    seen: set[str] = set()
    for file_path in files:
        try:
            node = json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{file_path}: invalid json: {exc}")
            continue

        extra = set(node) - ALLOWED_KEYS
        if extra:
            errors.append(f"{file_path}: unexpected keys {sorted(extra)}")

        node_id = node.get("node_id")
        if node_id in seen:
            errors.append(f"{file_path}: duplicate node_id {node_id}")
        seen.add(node_id)

        if node_id not in EXPECTED_NODES:
            errors.append(f"{file_path}: unexpected node_id {node_id}")
        if not str(node_id).startswith("repo_delivery."):
            errors.append(f"{file_path}: node_id must start with repo_delivery.")
        if node.get("authority_boundary") != "g2_required":
            errors.append(f"{file_path}: authority_boundary must be g2_required")
        if node.get("node_type") not in ALLOWED_NODE_TYPES:
            errors.append(f"{file_path}: invalid node_type {node.get('node_type')}")
        if node.get("canonical") not in ALLOWED_CANONICAL:
            errors.append(f"{file_path}: invalid canonical {node.get('canonical')}")

        gates = node.get("gates")
        if not isinstance(gates, list) or not gates:
            errors.append(f"{file_path}: gates must be a non-empty list")
        else:
            invalid = set(gates) - ALLOWED_GATES
            if invalid:
                errors.append(f"{file_path}: gates outside repo-delivery boundary {sorted(invalid)}")
            if "G2_EXECUTION" not in gates:
                errors.append(f"{file_path}: gates must include G2_EXECUTION")
            if len(gates) != len(set(gates)):
                errors.append(f"{file_path}: gates must be unique")

    missing = EXPECTED_NODES - seen
    if missing:
        errors.append(f"missing expected nodes: {sorted(missing)}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--family-dir", type=Path, default=Path("core/node-architect/node-catalog/repo_delivery"))
    args = parser.parse_args()
    errors = validate_family(args.family_dir)
    if errors:
        for error in errors:
            print(error)
        return 1
    print("REPO_DELIVERY_NODE_CATALOG_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
