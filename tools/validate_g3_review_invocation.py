#!/usr/bin/env python3
"""Validate G3 code-review-agent invocation evidence."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


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
    reviewer = record["reviewer"]
    invocation = record["invocation"]

    if reviewer["role"] != "code_reviewer":
        issues.append("reviewer.role must be code_reviewer")
    if reviewer["access_mode"] != "read_only":
        issues.append("reviewer.access_mode must be read_only")
    if reviewer["independence"] == "independent" and reviewer["agent_id"] == record["implementer_id"]:
        issues.append("independent code reviewer must differ from implementer")
    if invocation["requested_head_sha"] != head_sha:
        issues.append("invocation.requested_head_sha must match head_sha")
    if invocation["completed_head_sha"] != head_sha:
        issues.append("invocation.completed_head_sha must match head_sha")
    if record["write_actions"]:
        issues.append("code reviewer invocation must not perform write actions")

    if record["result"] == "pass":
        if record["stale"]:
            issues.append("result=pass requires stale=false")
        for finding in record["findings"]:
            if finding["severity"] == "BLOCKER" and finding["status"] != "resolved":
                issues.append(f"{finding['id']}: BLOCKER must be resolved before review pass")
            if finding["severity"] == "MAJOR" and finding["status"] not in {"resolved", "accepted_risk"}:
                issues.append(f"{finding['id']}: MAJOR must be resolved or accepted before review pass")
    return issues


def validate_record(record: Any, schema: dict[str, Any]) -> list[str]:
    issues = _schema_issues(record, schema)
    if issues or not isinstance(record, dict):
        return issues
    return _semantic_issues(record)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", required=True, type=Path)
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "schemas" / "g3-code-review-invocation.schema.json",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    try:
        record = _load_json(args.record)
        schema = _load_json(args.schema)
    except (OSError, json.JSONDecodeError) as exc:
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
