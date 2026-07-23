#!/usr/bin/env python3
"""Validate the scale_control controlled node catalog family."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
import yaml

EXPECTED_COUNT = 9
PREFIX = "scale_control."
REQUIRED_SEMANTICS = {
    "batch-admission-check", "batch-size-limit-check", "previous-batch-g5-verification",
    "catalog-cardinality-readiness", "execution-throttle-control", "workflow-run-observability",
    "exact-head-readiness-check", "rollout-progress-projection", "independent-audit-handoff",
}
ALLOWED_FIELDS = {"node_id", "node_type", "title", "description", "canonical", "authority_boundary", "gates"}
ALLOWED_TYPES = {"actor", "workflow", "gate", "tool", "schema", "state", "projection", "connector"}
ALLOWED_CANONICAL = {"canonical", "delivery_evidence", "audit_projection", "resume_hint"}
MATRIX_PATH = Path("core/node-architect/failure-simulation-matrix.json")


def validate_family(family_dir: Path, package_path: Path, matrix_path: Path) -> None:
    if not (family_dir / "README.md").exists():
        raise AssertionError("missing README.md")
    files = sorted(family_dir.glob("*.node.json"))
    if len(files) != EXPECTED_COUNT:
        raise AssertionError(f"expected {EXPECTED_COUNT} nodes, found {len(files)}")
    stems, ids, covered = set(), set(), set()
    for path in files:
        node = json.loads(path.read_text(encoding="utf-8"))
        if set(node) != ALLOWED_FIELDS:
            raise AssertionError(f"{path.name}: keys mismatch")
        stem = path.name.removesuffix(".node.json")
        stems.add(stem)
        if node["node_id"] != PREFIX + stem:
            raise AssertionError(f"{path.name}: node_id mismatch")
        if node["node_id"] in ids:
            raise AssertionError("duplicate node_id")
        ids.add(node["node_id"])
        if node["node_type"] not in ALLOWED_TYPES or node["canonical"] not in ALLOWED_CANONICAL:
            raise AssertionError(f"{path.name}: invalid type/canonical")

        gates = set(node["gates"])
        covered |= gates
        authority = node["authority_boundary"]
        canonical = node["canonical"]

        if canonical == "audit_projection":
            if authority != "read_only":
                raise AssertionError(f"{path.name}: audit projection authority must be read_only")
            if gates not in ({"G3_PR"}, {"G5_DEPLOY"}):
                raise AssertionError(f"{path.name}: projection applicability gate mismatch")
        elif gates == {"G3_PR"}:
            if authority != "g3_required":
                raise AssertionError(f"{path.name}: G3 control mapping mismatch")
        elif gates == {"G5_DEPLOY"}:
            if authority != "g5_required":
                raise AssertionError(f"{path.name}: G5 evidence mapping mismatch")
        else:
            raise AssertionError(f"{path.name}: unsupported gate mapping")

    if stems != REQUIRED_SEMANTICS:
        raise AssertionError(f"semantics mismatch: {sorted(stems)}")
    if covered != {"G3_PR", "G5_DEPLOY"}:
        raise AssertionError(f"gate coverage mismatch: {sorted(covered)}")

    package = yaml.safe_load(package_path.read_text(encoding="utf-8"))
    if package.get("package_version") != "1.16.0":
        raise AssertionError("package_version changed")
    entries = package.get("instructions", [])
    ids_all = [item["id"] for item in entries]
    paths = [item["path"] for item in entries]
    targets = [item["target"] for item in entries]
    if len(ids_all) != len(set(ids_all)) or len(paths) != len(set(paths)) or len(targets) != len(set(targets)):
        raise AssertionError("package ids/paths/targets must remain unique")
    scale_paths = {f"core/node-architect/node-catalog/scale_control/{stem}.node.json" for stem in REQUIRED_SEMANTICS}
    scale_paths.add("core/node-architect/node-catalog/scale_control/README.md")
    scale_paths.add("tools/node_architect/validate_node_catalog_scale_control.py")
    scale_paths.add("releases/changelog.d/2026-07-23-revamp-gwc-025-scale-control.md")
    if not scale_paths.issubset(set(paths)):
        raise AssertionError("package missing scale_control exports")
    node_exports = [path for path in paths if "/node-catalog/" in path and path.endswith(".node.json")]
    if len(node_exports) != 81:
        raise AssertionError(f"expected 81 exported nodes, found {len(node_exports)}")

    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    if matrix.get("scale_81_nodes_allowed") is not False:
        raise AssertionError("scale permission must remain false pending independent audit")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--family-dir", type=Path, default=Path("core/node-architect/node-catalog/scale_control"))
    parser.add_argument("--package", type=Path, default=Path("projects/gwc/package.yaml"))
    parser.add_argument("--matrix", type=Path, default=MATRIX_PATH)
    args = parser.parse_args(argv)
    try:
        validate_family(args.family_dir, args.package, args.matrix)
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("PASS: scale_control family and 81-node readiness are valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
