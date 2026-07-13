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


def _schema_issues(
    artifact_name: str,
    instance: Any,
    schema_path: Path,
) -> list[ValidationIssue]:
    schema = _load_json(schema_path)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    issues: list[ValidationIssue] = []
    for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.path)):
        location = ".".join(str(part) for part in error.path) or "<root>"
        issues.append(
            ValidationIssue(
                code="SCHEMA_VALIDATION_ERROR",
                artifact=artifact_name,
                location=location,
                message=error.message,
            )
        )
    return issues


def _cross_artifact_issues(artifacts: dict[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    g0 = artifacts["g0"]
    intake = artifacts["intake"]
    preflight = artifacts["preflight"]
    options = artifacts["options"]
    decision = artifacts["decision"]

    traces = {
        name: artifact.get("trace")
        for name, artifact in artifacts.items()
        if name != "g0"
    }
    reference_trace = traces["intake"]
    for name, trace in traces.items():
        if trace != reference_trace:
            issues.append(
                ValidationIssue(
                    code="TRACE_MISMATCH",
                    artifact=name,
                    location="trace",
                    message="All G1 artifacts must use the same trace object.",
                )
            )

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
                issues.append(
                    ValidationIssue(
                        code="G0_G1_CONTEXT_MISMATCH",
                        artifact="intake",
                        location=f"trace.{key}",
                        message=f"G1 trace {key} does not match the G0 snapshot.",
                    )
                )

    required_sources_missing = [
        item.get("path")
        for item in g0.get("sources", [])
        if item.get("required") and item.get("status") != "AVAILABLE"
    ]
    if g0.get("status") != "READY" or g0.get("blockers") or required_sources_missing:
        issues.append(
            ValidationIssue(
                code="G0_NOT_READY",
                artifact="g0",
                location="status",
                message="G0 must be READY with no blockers and all required sources available.",
            )
        )

    scope = intake.get("scope", {})
    criteria = intake.get("acceptance_criteria", [])
    if (
        intake.get("status") != "READY"
        or not scope.get("in_scope")
        or not scope.get("non_goals")
        or not criteria
        or intake.get("unresolved_questions")
    ):
        issues.append(
            ValidationIssue(
                code="G1_INTAKE_NOT_READY",
                artifact="intake",
                location="status",
                message="READY intake requires scope, non-goals, acceptance criteria, and no unresolved questions.",
            )
        )
    if any(not item.get("verifiable") for item in criteria):
        issues.append(
            ValidationIssue(
                code="G1_ACCEPTANCE_CRITERIA_NOT_VERIFIABLE",
                artifact="intake",
                location="acceptance_criteria",
                message="Every acceptance criterion must be verifiable.",
            )
        )

    failed_checks = [
        item.get("id")
        for item in preflight.get("checks", [])
        if item.get("status") == "FAIL"
    ]
    if preflight.get("outcome") != "PASS" or preflight.get("blockers") or failed_checks:
        issues.append(
            ValidationIssue(
                code="G1_PREFLIGHT_NOT_PASS",
                artifact="preflight",
                location="outcome",
                message="Preflight must PASS with no blockers or failed checks.",
            )
        )

    option_items = options.get("options", [])
    option_ids = [item.get("id") for item in option_items]
    if len(option_ids) != len(set(option_ids)):
        issues.append(
            ValidationIssue(
                code="G1_DUPLICATE_OPTION_ID",
                artifact="options",
                location="options",
                message="Option IDs must be unique.",
            )
        )
    if options.get("status") != "READY" or not option_items:
        issues.append(
            ValidationIssue(
                code="G1_OPTIONS_NOT_READY",
                artifact="options",
                location="status",
                message="Options must be READY and contain at least one option.",
            )
        )
    recommended = options.get("recommended_option_id")
    if recommended is not None and recommended not in option_ids:
        issues.append(
            ValidationIssue(
                code="G1_RECOMMENDED_OPTION_NOT_FOUND",
                artifact="options",
                location="recommended_option_id",
                message="The recommended option must exist in options.",
            )
        )

    selected = decision.get("selected_option_id")
    if selected not in option_ids:
        issues.append(
            ValidationIssue(
                code="G1_SELECTED_OPTION_NOT_FOUND",
                artifact="decision",
                location="selected_option_id",
                message="The selected option must exist in the options artifact.",
            )
        )

    criterion_ids = {item.get("id") for item in criteria}
    referenced_criteria = set(decision.get("acceptance_criteria_refs", []))
    if not referenced_criteria or not referenced_criteria.issubset(criterion_ids):
        issues.append(
            ValidationIssue(
                code="G1_ACCEPTANCE_REFERENCE_INVALID",
                artifact="decision",
                location="acceptance_criteria_refs",
                message="Decision acceptance criteria must reference intake criteria.",
            )
        )

    excluded = set(decision.get("authority_boundaries", {}).get("excluded", []))
    explicit_decision = decision.get("user_decision", {}).get("explicit") is True
    if (
        decision.get("status") != "ACCEPTED"
        or decision.get("g1_gate_outcome") != "PASS"
        or not explicit_decision
        or not REQUIRED_EXCLUDED_AUTHORITIES.issubset(excluded)
    ):
        issues.append(
            ValidationIssue(
                code="G1_DECISION_NOT_ACCEPTED",
                artifact="decision",
                location="status",
                message=(
                    "A PASS decision must be ACCEPTED, explicit, and exclude "
                    "G4 merge, G5 deploy, and G6 production authority."
                ),
            )
        )

    if decision.get("authority_boundaries", {}).get("grants"):
        issues.append(
            ValidationIssue(
                code="G1_AUTHORITY_GRANT_FORBIDDEN",
                artifact="decision",
                location="authority_boundaries.grants",
                message="A G1 decision cannot grant execution, merge, deploy, or production authority.",
            )
        )

    return issues


def validate_workspace(repo_root: Path, workspace: Path) -> ValidationReport:
    issues: list[ValidationIssue] = []
    artifacts: dict[str, Any] = {}

    for name, (relative_path, schema_name) in ARTIFACTS.items():
        artifact_path = workspace / relative_path
        schema_path = repo_root / "schemas" / schema_name
        if not artifact_path.is_file():
            issues.append(
                ValidationIssue(
                    code="MISSING_ARTIFACT",
                    artifact=name,
                    location=relative_path,
                    message=f"Required artifact is missing: {artifact_path}",
                )
            )
            continue
        if not schema_path.is_file():
            issues.append(
                ValidationIssue(
                    code="MISSING_SCHEMA",
                    artifact=name,
                    location=str(schema_path),
                    message=f"Required schema is missing: {schema_path}",
                )
            )
            continue
        try:
            artifact = _load_yaml(artifact_path)
            artifacts[name] = artifact
            issues.extend(_schema_issues(name, artifact, schema_path))
        except (OSError, ValueError, yaml.YAMLError, json.JSONDecodeError) as exc:
            issues.append(
                ValidationIssue(
                    code="ARTIFACT_LOAD_ERROR",
                    artifact=name,
                    location=relative_path,
                    message=str(exc),
                )
            )

    if len(artifacts) == len(ARTIFACTS) and not any(
        issue.code == "SCHEMA_VALIDATION_ERROR" for issue in issues
    ):
        issues.extend(_cross_artifact_issues(artifacts))

    return ValidationReport(outcome="PASS" if not issues else "BLOCKED", issues=issues)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=None,
        help="Repository root; defaults to the parent of tools/.",
    )
    parser.add_argument(
        "--workspace",
        default=".gwc",
        help="G0/G1 workspace path, relative to the repository root unless absolute.",
    )
    parser.add_argument("--json", action="store_true", help="Emit a JSON report.")
    args = parser.parse_args()

    repo_root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    workspace = Path(args.workspace)
    if not workspace.is_absolute():
        workspace = repo_root / workspace

    try:
        report = validate_workspace(repo_root, workspace.resolve())
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
