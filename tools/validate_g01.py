#!/usr/bin/env python3
"""Validate canonical G0/G1 lifecycle artifacts.

Exit codes:
- 0: artifacts are valid and the G1 gate evaluates to PASS.
- 1: artifacts are present but invalid, inconsistent, or blocked.
- 2: validator configuration or I/O failed.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sys
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker


ARTIFACTS: dict[str, tuple[str, str]] = {
    "g0": ("g0/context-snapshot.yaml", "g0-context-snapshot.schema.json"),
    "intake": ("g1/intake/g1-intake-brief.yaml", "g1-intake-brief.schema.json"),
    "preflight": ("g1/preflight/g1-preflight-report.yaml", "g1-preflight-report.schema.json"),
    "options": ("g1/brainstorming/g1-options.yaml", "g1-options.schema.json"),
    "decision": ("g1/decision/g1-decision-record.yaml", "g1-decision-record.schema.json"),
}

REQUIRED_EXCLUDED_AUTHORITIES = {"G4_MERGE", "G5_DEPLOY", "G6_PRODUCTION"}
GATE_ARTIFACTS: dict[str, str] = {
    "G2_EXECUTION": "g2/execution-envelope.yaml",
    "G3_PR": "g3/delivery-record.yaml",
    "G4_MERGE": "g4/merge-approval.yaml",
    "G5_DEPLOY": "g5/deployment-approval.yaml",
    "G6_PRODUCTION_DATA": "g6/production-approval.yaml",
}
NON_EXECUTABLE_CAPABILITY_STATES = {"UNKNOWN", "HARD_BLOCKED"}
BYPASS_ELIGIBLE = {"OPERATIONAL_ONLY", "MANUAL_CHECKPOINT_ONLY"}


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    artifact: str
    location: str
    message: str


@dataclass(frozen=True)
class ValidationReport:
    outcome: str
    issues: list[ValidationIssue]

    @property
    def valid(self) -> bool:
        return not self.issues and self.outcome == "PASS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "valid": self.valid,
            "issues": [asdict(issue) for issue in self.issues],
        }


def _load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _issue(code: str, artifact: str, location: str, message: str) -> ValidationIssue:
    return ValidationIssue(code=code, artifact=artifact, location=location, message=message)


def _schema_issues(artifact_name: str, instance: Any, schema_path: Path) -> list[ValidationIssue]:
    schema = _load_json(schema_path)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    issues: list[ValidationIssue] = []
    for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.path)):
        location = ".".join(str(part) for part in error.path) or "<root>"
        issues.append(_issue("SCHEMA_VALIDATION_ERROR", artifact_name, location, error.message))
    return issues


def validate_gate_artifact(workspace: Path, gate: str) -> list[ValidationIssue]:
    """Fail closed when an applicable downstream gate artifact is absent or malformed."""
    relative_path = GATE_ARTIFACTS.get(gate)
    if relative_path is None:
        return [_issue("GATE_SEQUENCE_INVALID", gate, "gate", f"Unsupported downstream gate: {gate}")]

    artifact_path = workspace / relative_path
    if not artifact_path.is_file():
        return [_issue("GATE_ARTIFACT_MISSING", gate, relative_path, f"Required gate artifact is missing: {artifact_path}")]

    try:
        artifact = _load_yaml(artifact_path)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return [_issue("GATE_ARTIFACT_INVALID", gate, relative_path, f"Gate artifact could not be loaded: {exc}")]

    if not isinstance(artifact, dict) or not artifact:
        return [_issue("GATE_ARTIFACT_INVALID", gate, relative_path, "Gate artifact must be a non-empty YAML object.")]
    return []


def _execution_feasibility_issues(preflight: dict[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    readback = preflight.get("process_readback", {})
    feasibility = preflight.get("execution_feasibility", {})
    route_steps = feasibility.get("route_steps", [])

    if readback.get("status") != "VERIFIED":
        issues.append(_issue(
            "G1_PROCESS_READBACK_INCOMPLETE",
            "preflight",
            "process_readback.status",
            "G1 PASS requires verified readback of the governing process and terminal outcome.",
        ))

    if not route_steps:
        issues.append(_issue(
            "G1_EXECUTION_ROUTE_MISSING",
            "preflight",
            "execution_feasibility.route_steps",
            "G1 requires an end-to-end route matrix through the declared terminal outcome.",
        ))
        return issues

    step_ids = [step.get("id") for step in route_steps]
    if len(step_ids) != len(set(step_ids)):
        issues.append(_issue(
            "G1_EXECUTION_ROUTE_DUPLICATE_STEP",
            "preflight",
            "execution_feasibility.route_steps",
            "Execution route step IDs must be unique.",
        ))

    blocked = [
        step.get("id")
        for step in route_steps
        if step.get("capability_status") in NON_EXECUTABLE_CAPABILITY_STATES
    ]
    if blocked:
        issues.append(_issue(
            "G1_EXECUTION_CAPABILITY_UNVERIFIED",
            "preflight",
            "execution_feasibility.route_steps",
            f"Mandatory route steps are not executable: {', '.join(str(item) for item in blocked)}.",
        ))

    missing_continuation = [
        step.get("id") for step in route_steps if not str(step.get("continuation", "")).strip()
    ]
    if missing_continuation or feasibility.get("continuation_coverage") != "COMPLETE":
        issues.append(_issue(
            "G1_CONTINUATION_COVERAGE_INCOMPLETE",
            "preflight",
            "execution_feasibility.continuation_coverage",
            "Every route step, including async and human-wait steps, requires a continuation rule.",
        ))

    outcome = feasibility.get("outcome")
    human_bypass_required = feasibility.get("human_bypass_required") is True
    bypass_steps = [
        step for step in route_steps if step.get("bypass_eligibility") in BYPASS_ELIGIBLE
    ]

    if outcome == "NOT_EXECUTABLE":
        issues.append(_issue(
            "G1_EXECUTION_NOT_FEASIBLE",
            "preflight",
            "execution_feasibility.outcome",
            "G1 cannot PASS when the requested terminal outcome is not executable.",
        ))
    if human_bypass_required and outcome != "EXECUTABLE_WITH_HUMAN_BYPASS":
        issues.append(_issue(
            "G1_HUMAN_BYPASS_OUTCOME_MISMATCH",
            "preflight",
            "execution_feasibility",
            "human_bypass_required=true requires EXECUTABLE_WITH_HUMAN_BYPASS.",
        ))
    if outcome == "EXECUTABLE_WITH_HUMAN_BYPASS" and not bypass_steps:
        issues.append(_issue(
            "G1_HUMAN_BYPASS_STEP_MISSING",
            "preflight",
            "execution_feasibility.route_steps",
            "A human-bypass outcome requires at least one explicitly eligible operational step.",
        ))
    if outcome == "EXECUTABLE" and human_bypass_required:
        issues.append(_issue(
            "G1_HUMAN_BYPASS_UNEXPECTED",
            "preflight",
            "execution_feasibility.human_bypass_required",
            "EXECUTABLE cannot require HUMAN BYPASS.",
        ))

    return issues


def _cross_artifact_issues(artifacts: dict[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    g0 = artifacts["g0"]
    intake = artifacts["intake"]
    preflight = artifacts["preflight"]
    options = artifacts["options"]
    decision = artifacts["decision"]

    traces = {name: artifact.get("trace") for name, artifact in artifacts.items() if name != "g0"}
    reference_trace = traces["intake"]
    for name, trace in traces.items():
        if trace != reference_trace:
            issues.append(_issue("TRACE_MISMATCH", name, "trace", "All G1 artifacts must use the same trace object."))

    repo = g0.get("repository", {})
    project = g0.get("project", {})
    if reference_trace:
        expected = {
            "project_id": project.get("id"),
            "repository": repo.get("full_name"),
            "base_sha": repo.get("base_sha"),
        }
        for key, value in expected.items():
            if reference_trace.get(key) != value:
                issues.append(_issue(
                    "G0_G1_CONTEXT_MISMATCH", "intake", f"trace.{key}",
                    f"G1 trace {key} does not match the G0 snapshot.",
                ))

    required_sources_missing = [
        item.get("path") for item in g0.get("sources", [])
        if item.get("required") and item.get("status") != "AVAILABLE"
    ]
    if g0.get("status") != "READY" or g0.get("blockers") or required_sources_missing:
        issues.append(_issue("G0_NOT_READY", "g0", "status", "G0 must be READY with no blockers and all required sources available."))

    scope = intake.get("scope", {})
    criteria = intake.get("acceptance_criteria", [])
    if (
        intake.get("status") != "READY"
        or not scope.get("in_scope")
        or not scope.get("non_goals")
        or not criteria
        or intake.get("unresolved_questions")
    ):
        issues.append(_issue(
            "G1_INTAKE_NOT_READY", "intake", "status",
            "READY intake requires scope, non-goals, acceptance criteria, and no unresolved questions.",
        ))
    if any(not item.get("verifiable") for item in criteria):
        issues.append(_issue(
            "G1_ACCEPTANCE_CRITERIA_NOT_VERIFIABLE", "intake", "acceptance_criteria",
            "Every acceptance criterion must be verifiable.",
        ))

    failed_checks = [item.get("id") for item in preflight.get("checks", []) if item.get("status") == "FAIL"]
    if preflight.get("outcome") != "PASS" or preflight.get("blockers") or failed_checks:
        issues.append(_issue(
            "G1_PREFLIGHT_NOT_PASS", "preflight", "outcome",
            "Preflight must PASS with no blockers or failed checks.",
        ))
    issues.extend(_execution_feasibility_issues(preflight))

    option_items = options.get("options", [])
    option_ids = [item.get("id") for item in option_items]
    if len(option_ids) != len(set(option_ids)):
        issues.append(_issue("G1_DUPLICATE_OPTION_ID", "options", "options", "Option IDs must be unique."))
    if options.get("status") != "READY" or not option_items:
        issues.append(_issue("G1_OPTIONS_NOT_READY", "options", "status", "Options must be READY and contain at least one option."))
    recommended = options.get("recommended_option_id")
    if recommended is not None and recommended not in option_ids:
        issues.append(_issue(
            "G1_RECOMMENDED_OPTION_NOT_FOUND", "options", "recommended_option_id",
            "The recommended option must exist in options.",
        ))

    selected = decision.get("selected_option_id")
    if selected not in option_ids:
        issues.append(_issue(
            "G1_SELECTED_OPTION_NOT_FOUND", "decision", "selected_option_id",
            "The selected option must exist in the options artifact.",
        ))

    criterion_ids = {item.get("id") for item in criteria}
    referenced_criteria = set(decision.get("acceptance_criteria_refs", []))
    if not referenced_criteria or not referenced_criteria.issubset(criterion_ids):
        issues.append(_issue(
            "G1_ACCEPTANCE_REFERENCE_INVALID", "decision", "acceptance_criteria_refs",
            "Decision acceptance criteria must reference intake criteria.",
        ))

    excluded = set(decision.get("authority_boundaries", {}).get("excluded", []))
    explicit_decision = decision.get("user_decision", {}).get("explicit") is True
    if (
        decision.get("status") != "ACCEPTED"
        or decision.get("g1_gate_outcome") != "PASS"
        or not explicit_decision
        or not REQUIRED_EXCLUDED_AUTHORITIES.issubset(excluded)
    ):
        issues.append(_issue(
            "G1_DECISION_NOT_ACCEPTED", "decision", "status",
            "A PASS decision must be ACCEPTED, explicit, and exclude G4 merge, G5 deploy, and G6 production authority.",
        ))

    if decision.get("authority_boundaries", {}).get("grants"):
        issues.append(_issue(
            "G1_AUTHORITY_GRANT_FORBIDDEN", "decision", "authority_boundaries.grants",
            "A G1 decision cannot grant execution, merge, deploy, or production authority.",
        ))
    return issues


def validate_workspace(repo_root: Path, workspace: Path, gate: str | None = None) -> ValidationReport:
    issues: list[ValidationIssue] = []
    artifacts: dict[str, Any] = {}

    for name, (relative_path, schema_name) in ARTIFACTS.items():
        artifact_path = workspace / relative_path
        schema_path = repo_root / "schemas" / schema_name
        if not artifact_path.is_file():
            issues.append(_issue("MISSING_ARTIFACT", name, relative_path, f"Required artifact is missing: {artifact_path}"))
            continue
        if not schema_path.is_file():
            issues.append(_issue("MISSING_SCHEMA", name, str(schema_path), f"Required schema is missing: {schema_path}"))
            continue
        try:
            artifact = _load_yaml(artifact_path)
            artifacts[name] = artifact
            issues.extend(_schema_issues(name, artifact, schema_path))
        except (OSError, ValueError, yaml.YAMLError, json.JSONDecodeError) as exc:
            issues.append(_issue("ARTIFACT_LOAD_ERROR", name, relative_path, str(exc)))

    if len(artifacts) == len(ARTIFACTS) and not any(issue.code == "SCHEMA_VALIDATION_ERROR" for issue in issues):
        issues.extend(_cross_artifact_issues(artifacts))
    if gate is not None:
        issues.extend(validate_gate_artifact(workspace, gate))

    return ValidationReport(outcome="PASS" if not issues else "BLOCKED", issues=issues)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=None, help="Repository root; defaults to the parent of tools/.")
    parser.add_argument("--workspace", default=".gwc", help="G0/G1 workspace path, relative to the repository root unless absolute.")
    parser.add_argument("--gate", choices=sorted(GATE_ARTIFACTS), default=None, help="Require the applicable downstream gate artifact in this task workspace.")
    parser.add_argument("--json", action="store_true", help="Emit a JSON report.")
    args = parser.parse_args()

    repo_root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    workspace = Path(args.workspace)
    if not workspace.is_absolute():
        workspace = repo_root / workspace

    try:
        report = validate_workspace(repo_root, workspace.resolve(), gate=args.gate)
    except Exception as exc:  # configuration-level failure
        if args.json:
            print(json.dumps({"outcome": "ERROR", "valid": False, "error": str(exc)}))
        else:
            print(f"ERROR: {exc}")
        return 2

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(f"G0/G1 validation outcome: {report.outcome}")
        for issue in report.issues:
            print(f"{issue.code}: {issue.artifact}:{issue.location}: {issue.message}")
    return 0 if report.valid else 1


if __name__ == "__main__":
    sys.exit(main())
