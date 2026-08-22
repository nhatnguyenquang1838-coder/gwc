#!/usr/bin/env python3
"""Validate the Node Architect Research -> Implementation bridge.

Exit codes:
  0: PASS
  1: schema or semantic validation failed
  2: input/configuration error
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
VALIDATION_SCHEMA = ROOT / "schemas" / "node-architect" / "research-implementation-validation.schema.json"
PLAN_SCHEMA = ROOT / "schemas" / "node-architect" / "implementation-plan.schema.json"

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
HUMAN_SCOPE_FIELDS = (
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
PLAN_SCOPE_FIELDS = (
    "research_parent",
    "target_repository",
    "planning_base_sha",
    "objective",
    "non_goals",
    "requirement_to_change",
    "work_packages",
    "safe_parallelism",
    "migration_backward_compatibility",
    "test_matrix",
    "observability",
    "rollback",
    "acceptance_criteria",
    "risks",
    "pr_slicing",
    "gate_path",
    "required_evidence_by_gate",
    "ownership_executor_assumptions",
)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
APPROVAL_RE = re.compile(
    r"^APPROVE RESEARCH_PLAN ([A-Z][A-Z0-9]*-\d+-\d{8}-R\d+) ([0-9a-f]{16})$"
)


def _canonical_hash(record: dict[str, Any], fields: tuple[str, ...]) -> str:
    payload = json.dumps(
        {field: record.get(field) for field in fields},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def compute_scope_hash(record: dict[str, Any]) -> str:
    """Return deterministic HUMAN_REVIEW_SCOPE_HASH."""
    return _canonical_hash(record, HUMAN_SCOPE_FIELDS)


def compute_plan_scope_hash(plan: dict[str, Any]) -> str:
    """Return deterministic implementation-plan scope hash."""
    return _canonical_hash(plan, PLAN_SCOPE_FIELDS)


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _schema_issues(record: Any, schema_path: Path) -> list[str]:
    schema = _load_json(schema_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    issues: list[str] = []
    for error in sorted(
        validator.iter_errors(record),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    ):
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        issues.append(f"schema:{location}: {error.message}")
    return issues


def validate_implementation_validation(
    record: dict[str, Any], current_main_sha: str | None = None
) -> list[str]:
    issues = _schema_issues(record, VALIDATION_SCHEMA)
    if issues or not isinstance(record, dict):
        return issues

    if record["classification"] not in VALID_CLASSIFICATIONS:
        issues.append("classification is not a supported research validation state")
    if current_main_sha is not None and record["current_main_sha"] != current_main_sha:
        issues.append("current main SHA drift invalidates implementation validation")

    verdicts = record["four_lens_verdicts"]
    if record["classification"] in HUMAN_REVIEW_CLASSIFICATIONS:
        if any(verdicts[lens] != "APPROVE" for lens in LENS_KEYS):
            issues.append("four lens review must be 4/4 APPROVE before Human review")
        if not record["implementation_surfaces"]:
            issues.append("validated research requires implementation_surfaces")
        if not record["acceptance_criteria"]:
            issues.append("validated research requires acceptance_criteria")
        if not record["assumptions_confirmed"]:
            issues.append("validated research requires at least one confirmed assumption")
        for field in (
            "test_strategy",
            "rollback_requirements",
            "observability_requirements",
        ):
            if not record[field]:
                issues.append(f"validated research requires {field}")

    if record["classification"] == "RESEARCH_VALIDATED_WITH_AMENDMENTS" and not record["amendments"]:
        issues.append("RESEARCH_VALIDATED_WITH_AMENDMENTS requires amendments")

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
    match = APPROVAL_RE.fullmatch(command.strip())
    if not match:
        return ["approval command must match exact APPROVE RESEARCH_PLAN syntax"]

    issues: list[str] = []
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
    issues = _schema_issues(plan, PLAN_SCHEMA)
    if issues or not isinstance(plan, dict):
        return issues

    packages = plan["work_packages"]
    ids = [item["id"] for item in packages]
    if len(ids) != len(set(ids)):
        issues.append("work package ids must be unique")
    known = set(ids)
    for item in packages:
        for dependency in item["depends_on"]:
            if dependency not in known:
                issues.append(f"{item['id']}: unknown dependency {dependency}")
            if dependency == item["id"]:
                issues.append(f"{item['id']}: work package cannot depend on itself")
    if _has_cycle(packages):
        issues.append("work package DAG must be acyclic")

    seen_parallel: set[str] = set()
    for group in plan["safe_parallelism"]:
        for work_package in group["work_packages"]:
            if work_package not in known:
                issues.append(
                    f"safe_parallelism {group['group_id']}: unknown work package {work_package}"
                )
            if work_package in seen_parallel:
                issues.append(
                    f"safe_parallelism: work package {work_package} appears in multiple groups"
                )
            seen_parallel.add(work_package)

    expected_gates = set(plan["gate_path"])
    evidence_gates = set(plan["required_evidence_by_gate"])
    if evidence_gates != expected_gates:
        missing = sorted(expected_gates - evidence_gates)
        extra = sorted(evidence_gates - expected_gates)
        if missing:
            issues.append("required_evidence_by_gate missing: " + ", ".join(missing))
        if extra:
            issues.append("required_evidence_by_gate has extra gates: " + ", ".join(extra))

    expected_hash = compute_plan_scope_hash(plan)
    if plan["implementation_scope_hash"] != expected_hash:
        issues.append("implementation_scope_hash does not match canonical plan scope")
    if plan["grants_execution_authority"] is not False:
        issues.append("implementation plan must not grant G2 execution authority")
    if plan["state"] != "IMPLEMENTATION_PLAN_READY":
        issues.append("state must be IMPLEMENTATION_PLAN_READY")
    if plan["next_state"] != "AWAITING_G2_AUTHORITY":
        issues.append("next_state must be AWAITING_G2_AUTHORITY")
    return issues


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)

    validation = sub.add_parser("validation")
    validation.add_argument("--record", required=True, type=Path)
    validation.add_argument("--current-main-sha", required=True)
    validation.add_argument("--json", action="store_true", dest="json_output")

    plan = sub.add_parser("plan")
    plan.add_argument("--record", required=True, type=Path)
    plan.add_argument("--json", action="store_true", dest="json_output")

    approval = sub.add_parser("approval")
    approval.add_argument("--command", required=True)
    approval.add_argument("--run-id", required=True)
    approval.add_argument("--scope-hash", required=True)
    approval.add_argument("--json", action="store_true", dest="json_output")
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
    except (OSError, json.JSONDecodeError, yaml.YAMLError, TypeError, KeyError, ValueError) as exc:
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
