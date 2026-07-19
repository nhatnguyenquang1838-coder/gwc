#!/usr/bin/env python3
"""Generate G1 options and capture an explicit G1 decision.

The command reads an existing G0/G1 workspace containing context, intake, and
preflight artifacts. It never grants merge, deployment, release, secret, or
production authority.

Exit codes:
- 0: decision is accepted and the complete G1 workspace validates to PASS.
- 1: artifacts are schema-valid, but the decision remains PENDING/REJECTED/BLOCKED.
- 2: input, schema, configuration, or I/O failure; no partial pair is reported written.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

AUTHORITY_EXCLUSIONS = ["G4_MERGE", "G5_DEPLOY", "G6_PRODUCTION"]


def _load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _validation_messages(instance: Any, schema_path: Path) -> list[str]:
    schema = _load_json(schema_path)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    messages: list[str] = []
    for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.path)):
        location = ".".join(str(part) for part in error.path) or "<root>"
        messages.append(f"{location}: {error.message}")
    return messages


def _scope_hash(intake: dict[str, Any]) -> str:
    payload = {
        "scope": intake.get("scope"),
        "constraints": intake.get("constraints"),
        "acceptance_criteria": intake.get("acceptance_criteria"),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _load_validator(repo_root: Path):
    path = repo_root / "tools" / "validate_g01.py"
    spec = importlib.util.spec_from_file_location("validate_g01_runtime", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load validator: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def generate_artifacts(
    decision_input: dict[str, Any],
    intake: dict[str, Any],
    preflight: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], str, list[str]]:
    generated_at = decision_input["generated_at"]
    option_items = decision_input["options"]
    option_ids = [item["id"] for item in option_items]
    criterion_ids = {item["id"] for item in intake.get("acceptance_criteria", [])}
    selected = decision_input["decision"]["selected_option_id"]
    requested_status = decision_input["decision"]["status"]
    explicit = decision_input["decision"]["explicit"] is True
    referenced = set(decision_input["decision"]["acceptance_criteria_refs"])
    semantic_issues: list[str] = []

    if len(option_ids) != len(set(option_ids)):
        semantic_issues.append("G1_DUPLICATE_OPTION_ID")
    recommended = decision_input["recommended_option_id"]
    if recommended is not None and recommended not in option_ids:
        semantic_issues.append("G1_RECOMMENDED_OPTION_NOT_FOUND")
    if selected is not None and selected not in option_ids:
        semantic_issues.append("G1_SELECTED_OPTION_NOT_FOUND")
    if not referenced or not referenced.issubset(criterion_ids):
        semantic_issues.append("G1_ACCEPTANCE_REFERENCE_INVALID")
    if preflight.get("outcome") != "PASS" or preflight.get("blockers"):
        semantic_issues.append("G1_PREFLIGHT_NOT_PASS")
    if requested_status == "ACCEPTED" and not explicit:
        semantic_issues.append("G1_EXPLICIT_DECISION_REQUIRED")

    trace = intake["trace"]
    options = {
        "schema_version": "1.0",
        "artifact_type": "g1-options",
        "generated_at": generated_at,
        "trace": trace,
        "options": option_items,
        "recommended_option_id": recommended,
        "recommendation_rationale": decision_input["recommendation_rationale"],
        "decision_required": True,
        "status": "READY",
    }

    if requested_status == "ACCEPTED" and not semantic_issues:
        status = "ACCEPTED"
        gate_outcome = "PASS"
    elif requested_status == "REJECTED":
        status = "REJECTED"
        gate_outcome = "REJECTED"
    else:
        status = "PENDING"
        gate_outcome = "BLOCKED" if semantic_issues else "NEEDS_INPUT"

    rejected = [option_id for option_id in option_ids if option_id != selected]
    decision = {
        "schema_version": "1.0",
        "artifact_type": "g1-decision-record",
        "generated_at": generated_at,
        "trace": trace,
        "options_ref": "../brainstorming/g1-options.yaml",
        "preflight_ref": "../preflight/g1-preflight-report.yaml",
        "status": status,
        "selected_option_id": selected,
        "user_decision": {
            "actor": decision_input["decision"]["actor"],
            "decided_at": decision_input["decision"]["decided_at"],
            "source": decision_input["decision"]["source"],
            "explicit": explicit,
        },
        "rationale": decision_input["decision"]["rationale"],
        "rejected_option_ids": rejected,
        "acceptance_criteria_refs": decision_input["decision"]["acceptance_criteria_refs"],
        "scope_hash": _scope_hash(intake),
        "g1_gate_outcome": gate_outcome,
        "authority_boundaries": {
            "grants": [],
            "excluded": AUTHORITY_EXCLUSIONS,
        },
        "subagent_distribution_plan": {
            "task_decomposition": [],
            "agent_allocation": [],
            "execution_order": [],
            "summary": "No subagent distribution required for this G1 decision capture.",
        },
    }
    outcome = "PASS" if status == "ACCEPTED" and gate_outcome == "PASS" else gate_outcome
    return options, decision, outcome, semantic_issues


def _write_yaml_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(yaml.safe_dump(value, sort_keys=False, allow_unicode=True), encoding="utf-8")
    temp.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--root", default=None)
    parser.add_argument("--workspace", default=".gwc")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = repo_root / input_path
    workspace = Path(args.workspace)
    if not workspace.is_absolute():
        workspace = repo_root / workspace

    try:
        decision_input = _load_yaml(input_path)
        input_errors = _validation_messages(
            decision_input, repo_root / "schemas" / "g01-decision-input.schema.json"
        )
        if input_errors:
            raise ValueError("decision input validation failed: " + " | ".join(input_errors))

        intake = _load_yaml(workspace / "g1/intake/g1-intake-brief.yaml")
        preflight = _load_yaml(workspace / "g1/preflight/g1-preflight-report.yaml")
        options, decision, outcome, semantic_issues = generate_artifacts(
            decision_input, intake, preflight
        )

        generated_errors: list[str, Any] = []
        generated_errors.extend(
            f"options: {message}"
            for message in _validation_messages(
                options, repo_root / "schemas" / "g1-options.schema.json"
            )
        )
        generated_errors.extend(
            f"decision: {message}"
            for message in _validation_messages(
                decision, repo_root / "schemas" / "g1-decision-record.schema.json"
            )
        )
        if generated_errors:
            raise ValueError("generated artifact validation failed: " + " | ".join(generated_errors))

        _write_yaml_atomic(workspace / "g1/brainstorming/g1-options.yaml", options)
        _write_yaml_atomic(workspace / "g1/decision/g1-decision-record.yaml", decision)

        validator = _load_validator(repo_root)
        report = validator.validate_workspace(repo_root, workspace.resolve())
        if outcome == "PASS" and not report.valid:
            outcome = "BLOCKED"
            semantic_issues.extend(issue.code for issue in report.issues)
    except (OSError, ValueError, TypeError, KeyError, yaml.YAMLError, json.JSONDecodeError) as exc:
        payload = {"outcome": "ERROR", "written": False, "error": str(exc)}
        print(json.dumps(payload, indent=2) if args.json else f"ERROR: {exc}")
        return 2

    payload = {
        "outcome": outcome,
        "written": True,
        "workspace": str(workspace.resolve()),
        "artifacts": [
            "g1/brainstorming/g1-options.yaml",
            "g1/decision/g1-decision-record.yaml",
        ],
        "issues": sorted(set(semantic_issues)),
        "scope_hash": decision["scope_hash"],
        "authority_grants": decision["authority_boundaries"]["grants"],
    }
    print(json.dumps(payload, indent=2) if args.json else f"G01 decision outcome: {outcome}")
    return 0 if outcome == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
