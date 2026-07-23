#!/usr/bin/env python3
"""Validate the failure_recovery controlled node catalog family."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

EXPECTED_COUNT = 9
PREFIX = "failure_recovery."
ALLOWED_FIELDS = {"node_id", "node_type", "title", "description", "canonical", "authority_boundary", "gates"}
REQUIRED_SEMANTICS = {
    "timeout-recovery", "crash-checkpoint-recovery", "stale-session-reconciliation",
    "unknown-write-reconciliation", "cas-mismatch-recovery", "lease-expiry-recovery",
    "approval-expiry-recovery", "duplicate-agent-fencing", "version-drift-rollback-routing",
}
ALLOWED_TYPES = {"actor", "workflow", "gate", "tool", "schema", "state", "projection", "connector"}
ALLOWED_CANONICAL = {"canonical", "delivery_evidence", "audit_projection", "resume_hint"}
ALLOWED_AUTH = {"g2_required", "g5_required"}
ALLOWED_GATES = {"G2_EXECUTION", "G5_DEPLOY"}
MATRIX_CASES = {
    "unknown_write_result_reconciles_before_retry", "cas_mismatch_reloads_checkpoint",
    "lease_expired_stops_or_reacquires", "approval_expired_regenerates_request",
    "duplicate_agent_blocked_by_lease", "node_version_drift_pins_or_restarts",
}


def validate_family(family_dir: Path, matrix_path: Path | None = None) -> None:
    if not family_dir.exists():
        raise AssertionError(f"missing family dir: {family_dir}")
    if not (family_dir / "README.md").exists():
        raise AssertionError("missing README.md")
    files = sorted(family_dir.glob("*.node.json"))
    if len(files) != EXPECTED_COUNT:
        raise AssertionError(f"expected {EXPECTED_COUNT} nodes, found {len(files)}")

    stems: set[str] = set()
    ids: set[str] = set()
    covered: set[str] = set()
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
        if node["node_type"] not in ALLOWED_TYPES:
            raise AssertionError(f"{path.name}: invalid node_type")
        if node["canonical"] not in ALLOWED_CANONICAL:
            raise AssertionError(f"{path.name}: invalid canonical")
        if node["authority_boundary"] not in ALLOWED_AUTH:
            raise AssertionError(f"{path.name}: invalid authority")
        gates = set(node["gates"])
        if not gates or not gates.issubset(ALLOWED_GATES):
            raise AssertionError(f"{path.name}: invalid gates")
        if node["authority_boundary"] == "g2_required" and gates != {"G2_EXECUTION"}:
            raise AssertionError(f"{path.name}: G2 authority mismatch")
        if node["authority_boundary"] == "g5_required" and gates != {"G5_DEPLOY"}:
            raise AssertionError(f"{path.name}: G5 authority mismatch")
        covered |= gates

    if stems != REQUIRED_SEMANTICS:
        raise AssertionError(f"semantics mismatch: {sorted(stems)}")
    if covered != ALLOWED_GATES:
        raise AssertionError(f"gate coverage mismatch: {sorted(covered)}")

    if matrix_path:
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        cases = {item["case_id"] for item in matrix["required_cases"]}
        missing = MATRIX_CASES - cases
        if missing:
            raise AssertionError(f"failure matrix missing cases: {sorted(missing)}")
        if matrix.get("scale_81_nodes_allowed") is not False:
            raise AssertionError("scale_81_nodes_allowed must remain false")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--family-dir", type=Path, default=Path("core/node-architect/node-catalog/failure_recovery"))
    parser.add_argument("--matrix", type=Path, default=Path("core/node-architect/failure-simulation-matrix.json"))
    args = parser.parse_args(argv)
    try:
        validate_family(args.family_dir, args.matrix)
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("PASS: failure_recovery node catalog family is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
