#!/usr/bin/env python3
"""Validate the Node Architect Research -> Implementation bridge.

Exit codes:
  0: PASS
  1: semantic validation failed
  2: input/configuration error
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

LENS_KEYS = (
    "L1_ARCHITECTURE_CORRECTNESS",
    "L2_SECURITY_TRUST",
    "L3_RELIABILITY_OPERABILITY",
    "L4_GOVERNANCE_IMPLEMENTABILITY",
)
VALID_CLASSIFICATIONS = {
    "RESEARCH_VALIDATED",
    "RESEARCH_VALIDATED_WITH_AMENDMENTS",
    "RESEARCH_STALE_REVIEW_REQUIRED",
    "RESEARCH_INVALIDATED",
    "AGENT_PREPARATION_BLOCKED",
}
HUMAN_REVIEW_CLASSIFICATIONS = {
    "RESEARCH_VALIDATED",
    "RESEARCH_VALIDATED_WITH_AMENDMENTS",
}
SCOPE_FIELDS = (
    "research_parent",
    "paired_github_issue",
    "s1_snapshot_sha",
    "current_main_sha",
    "four_lens_verdicts",
    "final_validated_recommendation",
    "amendments",
    "implementation_surfaces",
    "risks",
    "acceptance_criteria",
)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
APPROVAL_RE = re.compile(
    r"^APPROVE RESEARCH_PLAN ([A-Z][A-Z0-9]*-\d+-\d{8}-R\d+) ([0-9a-f]{16})$"
)


def _canonical_scope(record: dict[str, Any]) -> dict[str, Any]:
    return {field: record.get(field) for field in SCOPE_FIELDS}


def compute_scope_hash(record: dict[str, Any]) -> str:
    payload = json.dumps(
        _canonical_scope(record),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def validate_implementation_validation(
    record: dict[str, Any], current_main_sha: str | None = None
) -> list[str]:
    issues: list[str] = []
    required = {
        "schema_version",
        "artifact_type",
        "research_parent",
        "paired_github_issue",
        "s1_snapshot_sha",
        "current_main_sha",
        "four_lens_verdicts",
        "classification",
        "final_validated_recommendation",
        "amendments",
        "implementation_surfaces",
        "risks",
        "acceptance_criteria",
        "dependencies",
        "human_review_scope_hash",
    }
    missing = sorted(required - set(record))
    if missing:
        return ["missing required fields: " + ", ".join(missing)]

    if record["artifact_type"] != "implementation-validation":
        issues.append("artifact_type must be implementation-validation")
    if record["classification"] not in VALID_CLASSIFICATIONS:
        issues.append("classification is not a supported research validation state")
    for name in ("s1_snapshot_sha", "current_main_sha"):
        if not isinstance(record[name], str) or not SHA_RE.fullmatch(record[name]):
            issues.append(f"{name} must be a 40-character lowercase git SHA")
    if current_main_sha is not None and record["current_main_sha"] != current_main_sha:
        issues.append("current main SHA drift invalidates implementation validation")

    verdicts = record["four_lens_verdicts"]
    if not isinstance(verdicts, dict) or set(verdicts) != set(LENS_KEYS):
        issues.append("four lens verdicts must contain exactly L1-L4 canonical lenses")
    elif record["classification"] in HUMAN_REVIEW_CLASSIFICATIONS:
        if any(verdicts[lens] != "APPROVE" for lens in LENS_KEYS):
            issues.append("four lens review must be 4/4 APPROVE before Human review")

    if record["classification"] == "RESEARCH_VALIDATED_WITH_AMENDMENTS" and not record["amendments"]:
        issues.append("RESEARCH_VALIDATED_WITH_AMENDMENTS requires amendments")
    if record["classification"] in HUMAN_REVIEW_CLASSIFICATIONS:
        if not record["implementation_surfaces"]:
            issues.append("validated research requires implementation_surfaces")
        if not record["acceptance_criteria"]:
            issues.append("validated research requires acceptance_criteria")

    expected_hash = compute_scope_hash(record)
    if record["human_review_scope_hash"] != expected_hash:
        issues.append("human_review_scope_hash does not match canonical validated scope")

    for dependency in record["dependencies"]:
        if (
            str(dependency.get("status", "")).upper() == "DONE"
            and dependency.get("deliverable_evidence") is not True
        ):
            issues.append(
                f"{dependency.get('id', '<unknown>')}: Done without deliverable evidence is unsafe dependency evidence"
            )
    return issues


def validate_human_approval(
    command: str, *, expected_run_id: str, expected_scope_hash: str
) -> list[str]:
    issues: list[str] = []
    match = APPROVAL_RE.fullmatch(command.strip())
    if not match:
        return ["approval command must match exact APPROVE RESEARCH_PLAN syntax"]
    run_id, prefix = match.groups()
    if run_id != expected_run_id:
        issues.append("approval run id does not match current Human review run")
    if not HASH_RE.fullmatch(expected_scope_hash):
        issues.append("expected_scope_hash is not canonical sha256")
    else:
        expected_prefix = expected_scope_hash.split(":", 1)[1][:16]
        if prefix != expected_prefix:
            issues.append("approval scope hash prefix does not match current validated scope")
    return issues


def _has_cycle(packages: list[dict[str, Any]]) -> bool:
    graph = {item["id"]: list(item.get("depends_on", [])) for item in packages}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for dependency in graph.get(node, []):
            if dependency in graph and visit(dependency):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in graph)


def validate_implementation_plan(plan: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    required = {
        "schema_version",
        "artifact_type",
        "research_parent",
        "planning_base_sha",
        "implementation_scope_hash",
        "objective",
        "non_goals",
        "requirement_to_change",
        "work_packages",
        "test_matrix",
        "observability",
        "rollback",
        "acceptance_criteria",
        "risks",
        "pr_slicing",
        "gate_path",
        "grants_execution_authority",
        "state",
        "next_state",
    }
    missing = sorted(required - set(plan))
    if missing:
        return ["missing required fields: " + ", ".join(missing)]
    if plan["artifact_type"] != "implementation-plan":
        issues.append("artifact_type must be implementation-plan")
    if not SHA_RE.fullmatch(str(plan["planning_base_sha"])):
        issues.append("planning_base_sha must be a 40-character lowercase git SHA")
    if not HASH_RE.fullmatch(str(plan["implementation_scope_hash"])):
        issues.append("implementation_scope_hash must be canonical sha256")

    packages = plan["work_packages"]
    if not isinstance(packages, list) or not 3 <= len(packages) <= 7:
        issues.append("implementation plan requires 3 to 7 atomic work packages")
    else:
        ids = [item.get("id") for item in packages]
        if len(ids) != len(set(ids)) or any(not item for item in ids):
            issues.append("work package ids must be unique and non-empty")
        known = set(ids)
        for item in packages:
            for dependency in item.get("depends_on", []):
                if dependency not in known:
                    issues.append(f"{item.get('id')}: unknown dependency {dependency}")
                if dependency == item.get("id"):
                    issues.append(f"{item.get('id')}: work package cannot depend on itself")
        if _has_cycle(packages):
            issues.append("work package DAG must be acyclic")

    if plan["grants_execution_authority"] is not False:
        issues.append("implementation plan must not grant G2 execution authority")
    if plan["state"] != "IMPLEMENTATION_PLAN_READY":
        issues.append("state must be IMPLEMENTATION_PLAN_READY")
    if plan["next_state"] != "AWAITING_G2_AUTHORITY":
        issues.append("next_state must be AWAITING_G2_AUTHORITY")
    allowed_gate_paths = [
        ["G0", "G1", "G2", "G3", "G4", "G5"],
        ["G0", "G1", "G2", "G3", "G4", "G5", "G6"],
    ]
    if plan["gate_path"] not in allowed_gate_paths:
        issues.append("gate_path must preserve G0->G5 with optional G6")
    for field in (
        "requirement_to_change",
        "test_matrix",
        "observability",
        "rollback",
        "acceptance_criteria",
        "risks",
        "pr_slicing",
    ):
        if not plan[field]:
            issues.append(f"{field} must not be empty")
    return issues


def _load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    validation = sub.add_parser("validation")
    validation.add_argument("--record", required=True, type=Path)
    validation.add_argument("--current-main-sha", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--record", required=True, type=Path)
    approval = sub.add_parser("approval")
    approval.add_argument("--command", required=True)
    approval.add_argument("--run-id", required=True)
    approval.add_argument("--scope-hash", required=True)
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.mode == "validation":
            issues = validate_implementation_validation(
                _load_yaml(args.record), args.current_main_sha
            )
        elif args.mode == "plan":
            issues = validate_implementation_plan(_load_yaml(args.record))
        else:
            issues = validate_human_approval(
                args.command,
                expected_run_id=args.run_id,
                expected_scope_hash=args.scope_hash,
            )
    except (OSError, yaml.YAMLError, TypeError, KeyError, ValueError) as exc:
        report = {"status": "ERROR", "issues": [str(exc)]}
        print(json.dumps(report, indent=2) if args.json_output else f"ERROR: {exc}")
        return 2

    report = {"status": "PASS" if not issues else "FAIL", "issues": issues}
    if args.json_output:
        print(json.dumps(report, indent=2))
    elif issues:
        print("FAIL")
        for issue in issues:
            print(f"- {issue}")
    else:
        print("PASS")
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
