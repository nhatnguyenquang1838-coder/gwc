#!/usr/bin/env python3
"""Evaluate protected-base drift against the GWC base drift policy."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Iterable

import yaml
from jsonschema import Draft202012Validator, FormatChecker


POLICY_PATH = Path("governance/base-drift-policy.yaml")
SCHEMA_PATH = Path("schemas/base-drift-evaluation.schema.json")


def load_yaml(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def classify_changed_file(path: str) -> str:
    lowered = path.lower().replace("\\", "/")
    if lowered in {".env", ".env.example", ".env.local"} or "/.env" in lowered or lowered.endswith(".env"):
        return "STOP"
    if lowered.startswith(("core/", "schemas/", "tools/", "agents/", "registry/", "governance/")):
        if lowered.startswith(("governance/", "registry/")):
            return "REAPPROVE"
        if lowered.startswith(("core/",)):
            return "REAPPROVE"
        if lowered.startswith(("schemas/",)):
            return "REVALIDATE"
        if lowered.startswith(("tools/",)):
            return "REVALIDATE"
        return "REAPPROVE"
    if lowered.endswith((".md", ".rst", ".txt", ".yaml", ".yml")):
        return "SAFE_CONTINUE"
    if lowered.endswith((".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".c", ".cpp", ".cs")):
        return "REVALIDATE"
    if lowered.endswith((".json", ".toml", ".ini", ".cfg", ".lock")):
        return "REVALIDATE"
    return "SAFE_CONTINUE"


def choose_decision(changed_files: Iterable[str]) -> str:
    priority = ["STOP", "REAPPROVE", "REVALIDATE", "SAFE_CONTINUE"]
    decisions = {classify_changed_file(item) for item in changed_files}
    for item in priority:
        if item in decisions:
            return item
    return "SAFE_CONTINUE"


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    validator = Draft202012Validator(load_json(SCHEMA_PATH), format_checker=FormatChecker())
    for error in sorted(validator.iter_errors(payload), key=lambda e: list(e.path)):
        location = ".".join(str(piece) for piece in error.path) or "<root>"
        errors.append(f"{location}: {error.message}")
    return errors


def build_result(old_base_sha: str, new_base_sha: str, changed_files: list[str]) -> dict:
    decision = choose_decision(changed_files)
    risk_map = {
        "STOP": "STOP",
        "REAPPROVE": "REAPPROVE",
        "REVALIDATE": "REVALIDATE",
        "SAFE_CONTINUE": "SAFE_CONTINUE",
    }
    scope_overlap = {
        "STOP": "substantial",
        "REAPPROVE": "partial",
        "REVALIDATE": "partial",
        "SAFE_CONTINUE": "documented",
    }[decision]
    return {
        "old_base_sha": old_base_sha,
        "new_base_sha": new_base_sha,
        "changed_files": changed_files,
        "scope_overlap": scope_overlap,
        "risk_assessment": risk_map[decision],
        "evaluator_decision": decision,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-base-sha")
    parser.add_argument("--new-base-sha")
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()

    if args.test:
        tests = [
            (["README.md"], "SAFE_CONTINUE"),
            (["src/runtime.py"], "REVALIDATE"),
            (["core/policy.md"], "REAPPROVE"),
            ([".env"], "STOP"),
        ]
        for changed_files, expected in tests:
            decision = choose_decision(changed_files)
            if decision != expected:
                print(f"FAIL: {changed_files} -> {decision}, expected {expected}")
                return 1
        sample = build_result(
            "132304c74873d7f64651ebd3aa9ad639cd2aff92",
            "132304c74873d7f64651ebd3aa9ad639cd2aff93",
            ["README.md"],
        )
        errors = validate_payload(sample)
        if errors:
            print("\n".join(f"FAIL: {item}" for item in errors))
            return 1
        print("BASE DRIFT EVALUATOR TESTS PASSED")
        return 0

    if not args.old_base_sha or not args.new_base_sha:
        print("ERROR: --old-base-sha and --new-base-sha are required unless --test is used", file=sys.stderr)
        return 2

    changed_files = args.changed_file
    if not changed_files:
        print("ERROR: at least one --changed-file is required", file=sys.stderr)
        return 2

    result = build_result(args.old_base_sha, args.new_base_sha, changed_files)
    errors = validate_payload(result)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
