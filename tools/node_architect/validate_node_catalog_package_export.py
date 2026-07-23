#!/usr/bin/env python3
"""Validate the package_export controlled node catalog family."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REQUIRED_COUNT = 9
FAMILY_PREFIX = "package-export-"
ALLOWED_FIELDS = {"node_id", "node_type", "title", "canonical", "authority_boundary", "gates", "description"}
REQUIRED_FIELDS = {"node_id", "node_type", "title", "canonical", "authority_boundary", "gates"}
ALLOWED_GATES = {"G2_EXECUTION", "G3_PR"}
REQUIRED_SEMANTICS = {
    "package-manifest-load",
    "entry-schema-validation",
    "source-path-safety-check",
    "target-path-safety-check",
    "governance-tree-build",
    "export-manifest-generation",
    "deterministic-hash-verification",
    "smoke-verification",
    "export-failure-routing",
}


def validate_family(family_dir: Path) -> None:
    if not family_dir.exists():
        raise AssertionError(f"missing family dir: {family_dir}")

    node_files = sorted(family_dir.glob("*.node.json"))
    if len(node_files) != REQUIRED_COUNT:
        raise AssertionError(f"expected {REQUIRED_COUNT} nodes, found {len(node_files)}")

    seen: set[str] = set()
    covered_gates: set[str] = set()
    stems: set[str] = set()
    for path in node_files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        extra = set(payload) - ALLOWED_FIELDS
        if extra:
            raise AssertionError(f"{path}: unexpected fields {sorted(extra)}")
        missing = REQUIRED_FIELDS - set(payload)
        if missing:
            raise AssertionError(f"{path}: missing fields {sorted(missing)}")

        stem = path.name.removesuffix(".node.json")
        stems.add(stem)
        expected_id = FAMILY_PREFIX + stem
        if payload["node_id"] != expected_id:
            raise AssertionError(f"{path}: node_id mismatch")
        if payload["node_id"] in seen:
            raise AssertionError(f"{path}: duplicate node_id")
        seen.add(payload["node_id"])

        if payload["canonical"] != "delivery_evidence":
            raise AssertionError(f"{path}: canonical must be delivery_evidence")
        if payload["authority_boundary"] != "g2_required":
            raise AssertionError(f"{path}: authority_boundary must be g2_required")
        gates = set(payload["gates"])
        if not gates or not gates.issubset(ALLOWED_GATES):
            raise AssertionError(f"{path}: gates must be a non-empty subset of {sorted(ALLOWED_GATES)}")
        covered_gates.update(gates)

    if covered_gates != ALLOWED_GATES:
        raise AssertionError(f"family must cover both gates, got {sorted(covered_gates)}")
    missing_semantics = REQUIRED_SEMANTICS - stems
    if missing_semantics:
        raise AssertionError(f"missing required package export semantics: {sorted(missing_semantics)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--family-dir", type=Path, default=Path("core/node-architect/node-catalog/package_export"))
    args = parser.parse_args(argv)
    try:
        validate_family(args.family_dir)
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("PASS: package_export node catalog family is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
