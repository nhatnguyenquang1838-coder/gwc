#!/usr/bin/env python3
"""Validate a GWC G3 delivery record.

Exit codes:
  0: PASS
  1: schema or semantic validation failed
  2: input/schema load or configuration error
"""

from __future__ import annotations

import argparse
import json
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
    head_sha = record["head_sha"]
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

    if review["reviewed_head_sha"] != head_sha:
        issues.append("review.reviewed_head_sha must match head_sha")
    if review["reviewed_scope_hash"] != scope_hash:
        issues.append("review.reviewed_scope_hash must match scope_hash")
    if validation["head_sha"] != head_sha:
        issues.append("validation.head_sha must match head_sha")
    if ci["head_sha"] != head_sha:
        issues.append("ci.head_sha must match head_sha")

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
            elif acceptance["head_sha"] != head_sha:
                issues.append(
                    f"{finding['id']}: risk acceptance head_sha must match head_sha"
                )

    required_checks = [check for check in ci["checks"] if check["required"]]
    if ci["required"] and not required_checks:
        issues.append("ci.required=true requires at least one required check")
    for check in required_checks:
        if check["status"] != "pass":
            issues.append(f"required CI check {check['name']} must pass")

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
    issues = _schema_issues(record, schema)
    if issues or not isinstance(record, dict):
        return issues
    return _semantic_issues(record)


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
