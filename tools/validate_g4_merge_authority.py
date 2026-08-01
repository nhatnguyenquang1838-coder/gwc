#!/usr/bin/env python3
"""Validate G4 merge-authority receipt evidence."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = ROOT / "schemas" / "g4-merge-authority-receipt.schema.json"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def validate_record(record: Any, schema: dict[str, Any], now: datetime | None = None) -> list[str]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    issues = [
        f"schema:{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in validator.iter_errors(record)
    ]
    if issues or not isinstance(record, dict):
        return issues

    issued_at = parse_time(record["issued_at"])
    expires_at = parse_time(record["expires_at"])
    generated_at = parse_time(record["generated_at"])
    check_time = (now or generated_at).astimezone(timezone.utc)

    if expires_at <= issued_at:
        issues.append("expires_at must be later than issued_at")
    if generated_at < issued_at:
        issues.append("generated_at must not precede issued_at")
    if expires_at <= check_time:
        issues.append("G4 approval is expired")
    if record["pr_state"]["draft"]:
        issues.append("G4 authority requires PR Ready for Review")
    if record["authorized_action"] != "merge_pull_request":
        issues.append("G4 receipt may authorize only merge_pull_request")
    if record["manual_g5_action_authorized"] is not False:
        issues.append("G4 authority must not authorize manual G5 actions")
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    args = parser.parse_args(argv)

    try:
        record = load_json(args.record)
        schema = load_json(args.schema)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    issues = validate_record(record, schema)
    if issues:
        print("G4 MERGE AUTHORITY VALIDATION FAILED")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print("G4 MERGE AUTHORITY VALIDATION PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
