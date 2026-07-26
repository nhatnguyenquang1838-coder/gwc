#!/usr/bin/env python3
"""Validate normalized G5 post-merge status evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


SUCCESS = {"success"}
FAILURE = {"failure", "cancelled", "timed_out", "action_required"}


def load(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate(evidence: dict[str, Any], schema_path: Path) -> list[str]:
    schema = load(schema_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = [
        f"{'.'.join(str(part) for part in error.path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(evidence), key=lambda item: list(item.path))
    ]
    if errors:
        return errors
    merge_sha = evidence["merge_commit_sha"]
    runs = evidence["selected_runs"]
    required = set(evidence["required_workflows"])
    workflows = {run["workflow"] for run in runs}
    for run in runs:
        if run["head_sha"] != merge_sha:
            errors.append(f"selected run {run['run_id']} is not bound to merge SHA {merge_sha}")
    if evidence["manual_action_authorized"] is not False:
        errors.append("G5 status evidence must not authorize manual actions")
    classification = evidence["classification"]
    if classification == "success":
        missing = sorted(required - workflows)
        if missing:
            errors.append("success is missing required workflow evidence: " + ", ".join(missing))
        for run in runs:
            if run["conclusion"] not in SUCCESS:
                errors.append(f"success cannot include non-success run {run['run_id']}")
    elif classification == "CI_PENDING":
        if not runs:
            errors.append("CI_PENDING requires at least one exact-SHA observed run")
        if not evidence["checkpoint_required"] or "checkpoint_path" not in evidence:
            errors.append("CI_PENDING requires checkpoint evidence")
    elif classification == "CONNECTOR_OBSERVABILITY_INCOMPLETE":
        discovery = evidence["discovery"]
        if not discovery["exact_sha_lookup_attempted"]:
            errors.append("observability-incomplete requires exact SHA lookup attempt")
        if not discovery["fallbacks_attempted"]:
            errors.append("observability-incomplete requires fallback attempts")
    elif classification == "SHA_MISMATCH":
        if not any(item["reason"] == "sha_mismatch" for item in evidence["rejected_candidates"]):
            errors.append("SHA_MISMATCH requires a rejected candidate with reason sha_mismatch")
    elif classification == "failure":
        if not runs or not any(run["conclusion"] in FAILURE for run in runs):
            errors.append("failure requires exact-SHA failed or cancelled run evidence")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    try:
        errors = validate(load(args.evidence), args.root / "schemas/g5-status-evidence.schema.json")
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        errors = [str(exc)]
    if errors:
        print("G5 STATUS VALIDATION FAILED")
        for error in errors:
            print(f"- {error}")
        return 1
    print("G5 STATUS VALIDATION PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
