#!/usr/bin/env python3
"""Validate required GWC gate response trace fields and chronology."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker


def load(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle) if path.suffix.lower() == ".json" else yaml.safe_load(handle)


def parse_utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("timestamp must end with Z")
    return datetime.fromisoformat(value[:-1] + "+00:00")


def validate_trace(instance: Any, schema_path: Path) -> list[str]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = [
        f"{'.'.join(map(str, error.path)) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.path))
    ]
    if errors:
        return errors
    skills = instance["Skills called"]
    if any(not skill.strip() for skill in skills):
        errors.append("Skills called: values must not be blank")
    try:
        started = parse_utc(instance["Started at UTC"])
        ended = parse_utc(instance["Ended at UTC"])
        if ended < started:
            errors.append("Ended at UTC must be equal to or later than Started at UTC")
    except (TypeError, ValueError) as exc:
        errors.append(f"timestamp: {exc}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace")
    parser.add_argument("--root", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    try:
        errors = validate_trace(
            load(Path(args.trace)), root / "schemas/gate-response-trace.schema.json"
        )
    except (OSError, ValueError, yaml.YAMLError, json.JSONDecodeError) as exc:
        errors = [str(exc)]
    report = {
        "outcome": "PASS" if not errors else "FAIL",
        "valid": not errors,
        "errors": errors,
    }
    print(
        json.dumps(report, indent=2)
        if args.json
        else (
            "Gate response trace validation PASS"
            if not errors
            else "Gate response trace validation FAIL: " + "; ".join(errors)
        )
    )
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
