#!/usr/bin/env python3
"""Validate a GWC G3 delivery record and trusted current-PR-tip context.

The committed v1.1 record binds the immutable implementation subject. The
current PR tip, ancestry proof, evidence-only delta, and exact-tip CI results are
runtime facts and are deliberately not embedded in the record.

Exit codes:
  0: PASS
  1: schema, semantic, or runtime-context validation failed
  2: input/schema load or configuration error
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker


REQUIRED_LANES = {
    "requirement",
    "design",
    "code",
    "test",
    "governance",
    "delivery",
    "ci",
}
REQUIRED_EXCLUSIONS = {"G4_MERGE", "G5_DEPLOY", "G6_PRODUCTION_DATA"}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
LEGACY_ACTIVE_CLOSURE_ISSUE = (
    "legacy v1.0 delivery record requires migration to v1.1 for active G3 closure"
)


def _load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _schema_issues(record: Any, schema: dict[str, Any]) -> list[str]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    issues: list[str] = []
    for error in sorted(
        validator.iter_errors(record),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    ):
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        issues.append(f"schema:{location}: {error.message}")
    return issues


def _semantic_issues(record: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    implementation_head_sha = record["implementation_head_sha"]
    scope_hash = record["scope_hash"]
    review = record["review"]
    validation = record["validation"]
    ci = record["ci"]
    outcome = record["outcome"]

    if review["mode"] != "read-only":
        issues.append("review.mode must be read-only")

    if (
        review["independence"] == "independent"
        and review["reviewer_id"] == review["implementer_id"]
    ):
        issues.append("independent reviewer_id must differ from implementer_id")

    if review["reviewed_implementation_head_sha"] != implementation_head_sha:
        issues.append(
            "review.reviewed_implementation_head_sha must match implementation_head_sha"
        )
    if review["reviewed_scope_hash"] != scope_hash:
        issues.append("review.reviewed_scope_hash must match scope_hash")
    if validation["implementation_head_sha"] != implementation_head_sha:
        issues.append(
            "validation.implementation_head_sha must match implementation_head_sha"
        )

    lane_names = [lane["name"] for lane in review["lanes"]]
    if len(lane_names) != len(set(lane_names)):
        issues.append("review.lanes contains duplicate lane names")
    missing_lanes = sorted(REQUIRED_LANES - set(lane_names))
    extra_lanes = sorted(set(lane_names) - REQUIRED_LANES)
    if missing_lanes:
        issues.append(f"review.lanes missing required lanes: {', '.join(missing_lanes)}")
    if extra_lanes:
        issues.append(f"review.lanes contains unknown lanes: {', '.join(extra_lanes)}")

    for lane in review["lanes"]:
        if lane["applicable"] and lane["status"] == "not_applicable":
            issues.append(f"applicable lane {lane['name']} cannot be not_applicable")
        if not lane["applicable"] and lane["status"] != "not_applicable":
            issues.append(f"non-applicable lane {lane['name']} must be not_applicable")

    finding_ids = [finding["id"] for finding in review["findings"]]
    if len(finding_ids) != len(set(finding_ids)):
        issues.append("review.findings contains duplicate ids")

    for finding in review["findings"]:
        severity = finding["severity"]
        status = finding["status"]
        if outcome == "pass":
            if severity == "BLOCKER" and status != "resolved":
                issues.append(
                    f"{finding['id']}: BLOCKER must be resolved before G3 pass"
                )
            if severity == "MAJOR" and status not in {"resolved", "accepted_risk"}:
                issues.append(
                    f"{finding['id']}: MAJOR must be resolved or explicitly accepted"
                )
            if severity == "MINOR" and status == "open":
                issues.append(f"{finding['id']}: MINOR must be resolved or deferred")
        if status == "accepted_risk":
            acceptance = finding.get("risk_acceptance")
            if not acceptance:
                issues.append(
                    f"{finding['id']}: accepted_risk requires risk_acceptance evidence"
                )
            elif acceptance["implementation_head_sha"] != implementation_head_sha:
                issues.append(
                    f"{finding['id']}: risk acceptance implementation_head_sha "
                    "must match implementation_head_sha"
                )

    required_checks = ci["required_checks"]
    if ci["required"] and not required_checks:
        issues.append("ci.required=true requires at least one required check")

    exclusions = set(record["exclusions"])
    missing_exclusions = sorted(REQUIRED_EXCLUSIONS - exclusions)
    if missing_exclusions:
        issues.append(
            "exclusions missing later-gate boundaries: "
            + ", ".join(missing_exclusions)
        )

    if outcome == "pass":
        if not record["pull_request"]["draft"]:
            issues.append("outcome=pass requires a Draft Pull Request")
        if validation["status"] != "pass":
            issues.append("outcome=pass requires validation.status=pass")
        if review["decision"] != "pass":
            issues.append("outcome=pass requires review.decision=pass")
        if review["stale"]:
            issues.append("outcome=pass requires review.stale=false")
        for lane in review["lanes"]:
            if lane["applicable"] and lane["status"] != "pass":
                issues.append(
                    f"outcome=pass requires applicable lane {lane['name']} to pass"
                )
        for criterion in review["acceptance_criteria"]:
            if criterion["result"] not in {"pass", "not_applicable"}:
                issues.append(
                    f"outcome=pass requires {criterion['id']} to pass or be not_applicable"
                )
    elif review["decision"] == "pass":
        issues.append("review.decision=pass requires outcome=pass")

    if review["decision"] == "changes_required" and outcome != "fail":
        issues.append("review.decision=changes_required requires outcome=fail")
    if review["decision"] == "blocked" and outcome != "inconclusive":
        issues.append("review.decision=blocked requires outcome=inconclusive")

    return issues


def validate_record(
    record: Any,
    schema: dict[str, Any],
) -> list[str]:
    if isinstance(record, dict) and record.get("schema_version") == "1.0":
        return [LEGACY_ACTIVE_CLOSURE_ISSUE]
    issues = _schema_issues(record, schema)
    if issues or not isinstance(record, dict):
        return issues
    return _semantic_issues(record)


def _evidence_prefix(task_id: str) -> str:
    return f".gwc/tasks/{task_id}/g3/"


def validate_runtime_context(
    record: dict[str, Any],
    *,
    current_pr_head: str | None,
    implementation_ancestor_verified: bool,
    evidence_delta_paths: list[str],
    ci_checks: dict[str, str],
) -> list[str]:
    """Validate trusted facts that cannot safely live in the committed record."""
    issues: list[str] = []

    if record.get("schema_version") == "1.0":
        return [LEGACY_ACTIVE_CLOSURE_ISSUE]

    if not current_pr_head or not SHA_RE.fullmatch(current_pr_head):
        issues.append("current PR head must be supplied as a 40-hex SHA")
        return issues

    implementation_head_sha = record.get("implementation_head_sha")
    if not isinstance(implementation_head_sha, str) or not SHA_RE.fullmatch(
        implementation_head_sha
    ):
        issues.append("implementation_head_sha must be a 40-hex SHA")
        return issues

    if (
        current_pr_head != implementation_head_sha
        and not implementation_ancestor_verified
    ):
        issues.append(
            "implementation head must be verified as an ancestor of the current PR head"
        )

    task_id = record.get("task_id")
    if not isinstance(task_id, str) or not task_id:
        issues.append("task_id is required for evidence-only delta validation")
    else:
        prefix = _evidence_prefix(task_id)
        for path in evidence_delta_paths:
            if not path.startswith(prefix) or path == prefix:
                issues.append(
                    f"post-implementation path {path!r} violates evidence-only "
                    f"allowlist {prefix}**"
                )

    ci = record.get("ci")
    if not isinstance(ci, dict):
        issues.append("ci declaration is required")
        return issues

    required_checks = ci.get("required_checks", [])
    if ci.get("required") and not required_checks:
        issues.append("ci.required=true requires at least one required check")
    for name in required_checks:
        if ci_checks.get(name) != "pass":
            issues.append(f"required CI check {name} must pass at current PR head")

    return issues


def _parse_ci_checks(values: list[str]) -> tuple[dict[str, str], list[str]]:
    checks: dict[str, str] = {}
    issues: list[str] = []
    for value in values:
        if "=" not in value:
            issues.append(f"invalid --ci-check {value!r}; expected NAME=STATUS")
            continue
        name, status = value.split("=", 1)
        if not name or not status:
            issues.append(f"invalid --ci-check {value!r}; expected NAME=STATUS")
            continue
        checks[name] = status
    return checks, issues


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", required=True, type=Path)
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "schemas"
        / "g3-delivery-record.schema.json",
    )
    parser.add_argument(
        "--current-pr-head",
        help="Trusted current PR head SHA. Required for outcome=pass.",
    )
    parser.add_argument(
        "--implementation-ancestor-verified",
        action="store_true",
        help="Assert trusted repository evidence verified implementation head ancestry.",
    )
    parser.add_argument(
        "--evidence-delta-path",
        action="append",
        default=[],
        help="Path changed after implementation head; repeat for each path.",
    )
    parser.add_argument(
        "--ci-check",
        action="append",
        default=[],
        metavar="NAME=STATUS",
        help="Trusted current-tip CI result; repeat for each check.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        record = _load_yaml(args.record)
        schema = _load_json(args.schema)
    except (OSError, json.JSONDecodeError, yaml.YAMLError) as exc:
        report = {"status": "ERROR", "issues": [str(exc)]}
        if args.json_output:
            print(json.dumps(report, indent=2))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    issues = validate_record(record, schema)
    ci_checks, ci_arg_issues = _parse_ci_checks(args.ci_check)
    issues.extend(ci_arg_issues)

    if (
        not issues
        and isinstance(record, dict)
        and record.get("schema_version") == "1.1"
        and record.get("outcome") == "pass"
    ):
        issues.extend(
            validate_runtime_context(
                record,
                current_pr_head=args.current_pr_head,
                implementation_ancestor_verified=args.implementation_ancestor_verified,
                evidence_delta_paths=args.evidence_delta_path,
                ci_checks=ci_checks,
            )
        )

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
