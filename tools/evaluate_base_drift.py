#!/usr/bin/env python3
"""Evaluate protected-base drift against the GWC base drift policy.

The evaluator intentionally separates authority validity from evidence freshness.
A protected-base SHA change creates an interrupt frame, but only REAPPROVE or
STOP invalidate the active envelope. SAFE_CONTINUE and REVALIDATE may preserve
G2 authority when the approved scope, risk, task, branch, and authorized actions
remain unchanged.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Iterable

import yaml
from jsonschema import Draft202012Validator, FormatChecker


POLICY_PATH = Path("governance/base-drift-policy.yaml")
SCHEMA_PATH = Path("schemas/base-drift-evaluation.schema.json")

PRIORITY = ["STOP", "REAPPROVE", "REVALIDATE", "SAFE_CONTINUE"]


def load_yaml(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _normalize(path: str) -> str:
    return path.lower().replace("\\", "/")


def classify_changed_file(path: str) -> tuple[str, str]:
    lowered = _normalize(path)
    if lowered in {".env", ".env.example", ".env.local"} or "/.env" in lowered or lowered.endswith(".env"):
        return "STOP", "SECRET_OR_PRODUCTION_BOUNDARY"
    if lowered.startswith(("production/", "deploy/production/")):
        return "STOP", "SECRET_OR_PRODUCTION_BOUNDARY"
    if lowered.startswith(("core/", "agents/", "registry/", "governance/")):
        return "REAPPROVE", "GOVERNANCE_SOURCE_CHANGE"
    if lowered.startswith((".github/workflows/", "workflows/")):
        return "REAPPROVE", "REQUIRED_WORKFLOW_CHANGE"
    if lowered.startswith(("schemas/", "tools/")):
        return "REVALIDATE", "VALIDATOR_OR_SCHEMA_CHANGE"
    if lowered.endswith(("package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "poetry.lock", "requirements.txt")):
        return "REVALIDATE", "TRANSITIVE_DEPENDENCY_CHANGE"
    if lowered.endswith((".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".c", ".cpp", ".cs")):
        return "REVALIDATE", "TRANSITIVE_DEPENDENCY_CHANGE"
    if lowered.endswith((".json", ".toml", ".ini", ".cfg", ".lock")):
        return "REVALIDATE", "VALIDATOR_OR_SCHEMA_CHANGE"
    return "SAFE_CONTINUE", "UNRELATED_PATH_CHANGE"


def _path_overlaps_scope(path: str, approved_scope: Iterable[str]) -> bool:
    normalized = _normalize(path)
    for item in approved_scope:
        scope = _normalize(item).rstrip("/")
        if not scope:
            continue
        if normalized == scope or normalized.startswith(scope + "/") or scope.startswith(normalized + "/"):
            return True
    return False


def choose_decision(changed_files: Iterable[str], approved_scope: Iterable[str] = ()) -> tuple[str, list[str]]:
    decisions: set[str] = set()
    reason_codes: set[str] = set()
    approved_scope = list(approved_scope)

    for item in changed_files:
        decision, reason = classify_changed_file(item)
        decisions.add(decision)
        reason_codes.add(reason)
        if approved_scope and _path_overlaps_scope(item, approved_scope):
            reason_codes.add("APPROVED_SCOPE_OVERLAP")
            if decision == "SAFE_CONTINUE":
                decisions.add("REVALIDATE")

    for item in PRIORITY:
        if item in decisions:
            return item, sorted(reason_codes)
    return "SAFE_CONTINUE", ["UNRELATED_PATH_CHANGE"]


def _effects_for_decision(decision: str) -> tuple[dict, dict, dict]:
    if decision == "SAFE_CONTINUE":
        authority = {"g2": "PRESERVED", "g3": "PRESERVED", "g4": "PRESERVED", "g5": "NOT_APPLICABLE", "g6": "NOT_APPLICABLE"}
        evidence = {"invalidated": [], "preserved": ["g2_authority", "g3_review", "exact_head_ci", "g4_readiness"]}
        continuation = {"interrupt_required": True, "next_mode": "RESUME_PARENT", "requires_human_approval": False, "required_checks": []}
    elif decision == "REVALIDATE":
        authority = {"g2": "PRESERVED_PENDING_REVALIDATION", "g3": "REFRESH_REQUIRED", "g4": "REFRESH_REQUIRED", "g5": "NOT_APPLICABLE", "g6": "NOT_APPLICABLE"}
        evidence = {"invalidated": ["affected_validation", "candidate_integration", "mergeability"], "preserved": ["g2_authority"]}
        continuation = {"interrupt_required": True, "next_mode": "RESUME_PARENT", "requires_human_approval": False, "required_checks": ["affected_validation", "candidate_integration"]}
    elif decision == "REAPPROVE":
        authority = {"g2": "INVALIDATED", "g3": "INVALIDATED", "g4": "INVALIDATED", "g5": "NOT_APPLICABLE", "g6": "NOT_APPLICABLE"}
        evidence = {"invalidated": ["g2_authority", "g3_review", "g4_readiness"], "preserved": ["audit_history"]}
        continuation = {"interrupt_required": True, "next_mode": "REROUTE_REAPPROVE", "requires_human_approval": True, "required_checks": []}
    else:
        authority = {"g2": "INVALIDATED", "g3": "INVALIDATED", "g4": "INVALIDATED", "g5": "INVALIDATED", "g6": "INVALIDATED"}
        evidence = {"invalidated": ["active_route"], "preserved": ["blocker_evidence", "audit_history"]}
        continuation = {"interrupt_required": True, "next_mode": "STOP", "requires_human_approval": False, "required_checks": []}
    return authority, evidence, continuation


def _scope_overlap(decision: str, reason_codes: list[str]) -> str:
    if "APPROVED_SCOPE_OVERLAP" in reason_codes:
        return "full" if decision in {"REAPPROVE", "STOP"} else "partial"
    return {
        "STOP": "substantial",
        "REAPPROVE": "partial",
        "REVALIDATE": "partial",
        "SAFE_CONTINUE": "none",
    }[decision]


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    validator = Draft202012Validator(load_json(SCHEMA_PATH), format_checker=FormatChecker())
    for error in sorted(validator.iter_errors(payload), key=lambda e: list(e.path)):
        location = ".".join(str(piece) for piece in error.path) or "<root>"
        errors.append(f"{location}: {error.message}")
    return errors


def build_result(old_base_sha: str, new_base_sha: str, changed_files: list[str], approved_scope: list[str] | None = None) -> dict:
    decision, reason_codes = choose_decision(changed_files, approved_scope or [])
    authority, evidence, continuation = _effects_for_decision(decision)
    return {
        "old_base_sha": old_base_sha,
        "new_base_sha": new_base_sha,
        "changed_files": changed_files,
        "scope_overlap": _scope_overlap(decision, reason_codes),
        "risk_assessment": decision,
        "evaluator_decision": decision,
        "reason_codes": reason_codes,
        "authority_effect": authority,
        "evidence_effect": evidence,
        "continuation": continuation,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-base-sha")
    parser.add_argument("--new-base-sha")
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--approved-scope", action="append", default=[])
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()

    if args.test:
        tests = [
            (["README.md"], [], "SAFE_CONTINUE"),
            (["src/runtime.py"], [], "REVALIDATE"),
            (["core/policy.md"], [], "REAPPROVE"),
            ([".env"], [], "STOP"),
            (["docs/base-drift-policy.md"], ["docs/base-drift-policy.md"], "REVALIDATE"),
        ]
        for changed_files, approved_scope, expected in tests:
            decision, _ = choose_decision(changed_files, approved_scope)
            if decision != expected:
                print(f"FAIL: {changed_files} with scope {approved_scope} -> {decision}, expected {expected}")
                return 1
        sample = build_result(
            "132304c74873d7f64651ebd3aa9ad639cd2aff92",
            "132304c74873d7f64651ebd3aa9ad639cd2aff93",
            ["README.md"],
            [],
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
    if not args.changed_file:
        print("ERROR: at least one --changed-file is required", file=sys.stderr)
        return 2

    result = build_result(args.old_base_sha, args.new_base_sha, args.changed_file, args.approved_scope)
    errors = validate_payload(result)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
