#!/usr/bin/env python3
"""Validate GWC interrupt-flow schemas and base-drift sample frames."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator, FormatChecker


FRAME_SCHEMA = Path("schemas/interrupt-frame.schema.json")
NODE_SCHEMA = Path("schemas/node-interruptibility.schema.json")


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise AssertionError(f"{path}: expected JSON object")
    return value


def validate(schema_path: Path, instance: dict) -> list[str]:
    schema = load_json(schema_path)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors: list[str] = []
    for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.path)):
        location = ".".join(str(piece) for piece in error.path) or "<root>"
        errors.append(f"{location}: {error.message}")
    return errors


def sample_frame(decision: str = "REVALIDATE") -> dict:
    return {
        "schema_version": "1.0",
        "interrupt_id": "INT-BASE-DRIFT-001",
        "interrupt_type": "BASE_DRIFT",
        "state": "HANDLING",
        "task_id": "SCRUM-74",
        "gate": "G2_EXECUTION",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "branch": "feat/base-drift-interrupt-flow",
        "approved_base_sha": "14545de1f96ad7cab8c675cdf8aebfe5f80caa4b",
        "observed_base_sha": "24545de1f96ad7cab8c675cdf8aebfe5f80caa4b",
        "working_head_sha": "34545de1f96ad7cab8c675cdf8aebfe5f80caa4b",
        "scope_hash": "sha256:e1b014369c7284a47bc541788769b477ea5aadb31a3750f3e98aa6f1af69416e",
        "parent": {
            "node_id": "runtime_checkpoint.checkpoint-persist",
            "node_version": "1.0",
            "phase": "PRE_ACTION",
            "checkpoint_id": "CKP-BASE-DRIFT-001",
            "side_effect_state": "NOT_STARTED"
        },
        "assessment": {
            "decision": decision,
            "reason_codes": ["VALIDATOR_OR_SCHEMA_CHANGE"],
            "affected_gates": ["G2_EXECUTION", "G3_PR"],
            "affected_evidence": ["affected_validation", "candidate_integration"]
        },
        "continuation": {
            "on_pass": "RESUME_PARENT",
            "on_fail": "REROUTE_REAPPROVE",
            "resume_verification_required": True,
            "target_node": "runtime_checkpoint.base-drift-revalidate"
        },
        "audit_events": ["base_drift_detected", "parent_node_suspended"]
    }


def sample_node() -> dict:
    return {
        "schema_version": "1.0",
        "node_id": "runtime_checkpoint.base-drift-revalidate",
        "interruptibility": {
            "BASE_DRIFT": {
                "supported": True,
                "safe_phases": ["PRE_ACTION", "POST_ACTION_READBACK"],
                "forbidden_phases": ["SIDE_EFFECT_IN_FLIGHT"],
                "checkpoint_required": True,
                "resume_strategy": "FROM_CHECKPOINT"
            }
        }
    }


def run_tests() -> None:
    frame_errors = validate(FRAME_SCHEMA, sample_frame())
    node_errors = validate(NODE_SCHEMA, sample_node())
    errors = frame_errors + node_errors
    if errors:
        raise AssertionError("\n".join(errors))

    unsafe = sample_frame("STOP")
    unsafe["continuation"]["on_pass"] = "RESUME_PARENT"
    if not unsafe["assessment"]["decision"] == "STOP":
        raise AssertionError("sample STOP decision was not constructed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()
    if args.test:
        run_tests()
        print("INTERRUPT FLOW VALIDATION PASSED")
        return 0
    print("Use --test to validate bundled interrupt-flow samples.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
