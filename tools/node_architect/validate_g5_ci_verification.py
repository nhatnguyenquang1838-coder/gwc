#!/usr/bin/env python3
"""Validate G5 CI verification evidence and checkpoints.

This validator is intentionally data-oriented. It does not call GitHub and does
not execute repository-controlled code. It validates an already-collected G5
status bundle against exact-SHA and no-false-pass invariants.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_SCHEMA = REPO_ROOT / "schemas" / "g5-ci-verification-evidence.schema.json"
CHECKPOINT_SCHEMA = REPO_ROOT / "schemas" / "node-architect" / "g5-ci-checkpoint.schema.json"

TERMINAL_SUCCESS = {"success"}
TERMINAL_FAILURE = {"failure", "cancelled", "timed_out", "action_required"}
PENDING_STATUS = {"queued", "waiting", "requested", "in_progress"}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def schema_errors(instance: Any, schema_path: Path) -> list[str]:
    schema = load_json(schema_path)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [f"{'.'.join(str(part) for part in error.path) or '<root>'}: {error.message}" for error in validator.iter_errors(instance)]


def semantic_errors(evidence: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    merge_sha = evidence["merge_commit_sha"]
    classification = evidence["classification"]
    selected_runs = evidence.get("selected_runs", [])
    required = [item["name"] for item in evidence.get("required_workflows", []) if item.get("required")]
    selected_workflows = {run["workflow"] for run in selected_runs}

    for run in selected_runs:
        if run["head_sha"] != merge_sha:
            errors.append(f"selected run {run['run_id']} is not bound to merge SHA {merge_sha}")

    if evidence["manual_action_authorized"] is not False:
        errors.append("G5_STATUS_VERIFY evidence must not authorize manual actions")

    if classification == "success":
        missing = sorted(set(required) - selected_workflows)
        if missing:
            errors.append("success is missing required workflow evidence: " + ", ".join(missing))
        for run in selected_runs:
            if run.get("conclusion") not in TERMINAL_SUCCESS:
                errors.append(f"success cannot include non-success run {run['run_id']}")
        if evidence.get("checkpoint_required"):
            errors.append("success cannot require a pending checkpoint")

    if classification == "CI_PENDING":
        if not selected_runs:
            errors.append("CI_PENDING requires at least one exact-SHA observed run")
        if not evidence.get("checkpoint_required"):
            errors.append("CI_PENDING requires checkpoint_required=true")
        if not evidence.get("checkpoint_path"):
            errors.append("CI_PENDING requires checkpoint_path")

    if classification == "CONNECTOR_OBSERVABILITY_INCOMPLETE":
        discovery = evidence.get("discovery", {})
        if not discovery.get("exact_sha_lookup_attempted"):
            errors.append("observability-incomplete requires exact SHA lookup attempt")
        if not discovery.get("fallbacks_attempted"):
            errors.append("observability-incomplete requires fallback attempts")

    if classification == "SHA_MISMATCH":
        if not any(item.get("reason") == "sha_mismatch" for item in evidence.get("rejected_candidates", [])):
            errors.append("SHA_MISMATCH requires a rejected candidate with reason sha_mismatch")

    if classification == "failure":
        if not selected_runs:
            errors.append("failure requires exact-SHA selected run evidence")
        if not any(run.get("conclusion") in TERMINAL_FAILURE for run in selected_runs):
            errors.append("failure requires at least one terminal failed/cancelled/timed-out/action_required run")

    return errors


def validate_checkpoint(path: Path) -> list[str]:
    checkpoint = load_json(path)
    errors = schema_errors(checkpoint, CHECKPOINT_SCHEMA)
    if checkpoint.get("attempt", 0) > checkpoint.get("max_attempts", 0):
        errors.append("attempt cannot exceed max_attempts")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path, help="Path to G5 CI evidence JSON")
    parser.add_argument("--checkpoint", type=Path, help="Optional checkpoint JSON")
    args = parser.parse_args(argv)

    evidence = load_json(args.evidence)
    errors = schema_errors(evidence, EVIDENCE_SCHEMA)
    errors.extend(semantic_errors(evidence))
    if args.checkpoint:
        errors.extend(validate_checkpoint(args.checkpoint))

    if errors:
        print("G5 CI VERIFICATION VALIDATION FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("G5 CI VERIFICATION VALIDATION PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
