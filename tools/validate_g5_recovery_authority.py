#!/usr/bin/env python3
"""Validate a human-authorized G5 bootstrap recovery receipt."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

REQUIRED_WORKFLOWS = {"Validate instructions", "Build instruction packages"}


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def validate_record(record: dict[str, Any], schema: dict[str, Any], *, now: datetime | None = None) -> list[str]:
    issues = [
        f"schema:{'.'.join(str(p) for p in error.path) or '<root>'}: {error.message}"
        for error in sorted(
            Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(record),
            key=lambda item: list(item.path),
        )
    ]
    if issues:
        return issues

    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    issued = _parse_time(record["issued_at"])
    expires = _parse_time(record["expires_at"])
    merged_at = _parse_time(record["merged_pr"]["merged_at"])
    if expires <= issued:
        issues.append("semantic: expires_at must be after issued_at")
    if expires <= now:
        issues.append("semantic: recovery authority is expired")
    if merged_at > issued:
        issues.append("semantic: recovery authority must be issued after the historical merge")
    if record["approved_head_sha"] == record["merge_commit_sha"]:
        issues.append("semantic: approved head and merge commit must be distinct Git objects")

    workflows = record["required_workflows"]
    names = {item["workflow"] for item in workflows}
    run_ids = [item["run_id"] for item in workflows]
    if names != REQUIRED_WORKFLOWS:
        issues.append("semantic: exactly the two canonical required workflows must be present")
    if len(run_ids) != len(set(run_ids)):
        issues.append("semantic: workflow run IDs must be distinct")
    for item in workflows:
        if item["head_sha"] != record["merge_commit_sha"]:
            issues.append(f"semantic: {item['workflow']} head_sha does not match merge_commit_sha")

    expected_artifact = (
        f"g5-recovery-pr-{record['pr_number']}-merge-"
        f"{record['merge_commit_sha'][:12]}-{record['recovery_id']}"
    )
    if record["canonical_artifact_name"] != expected_artifact:
        issues.append("semantic: canonical_artifact_name does not match exact PR/merge/recovery binding")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record")
    parser.add_argument("--schema", default=None)
    parser.add_argument("--now", default=None, help="Optional ISO-8601 UTC test time")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    schema_path = Path(args.schema) if args.schema else root / "schemas" / "g5-recovery-authority.schema.json"
    try:
        record = json.loads(Path(args.record).read_text(encoding="utf-8"))
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        now = _parse_time(args.now) if args.now else None
        issues = validate_record(record, schema, now=now)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 2
    if issues:
        for issue in issues:
            print(issue)
        return 1
    print("G5 recovery authority validation: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
