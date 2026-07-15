#!/usr/bin/env python3
"""Validate hotfix/rescue mode G0 intake artifacts.

Exit codes:
- 0: intake artifact is valid for hotfix/rescue execution
- 1: intake artifact is present but invalid or missing required fields
- 2: validator configuration or I/O failed
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

import yaml


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


def validate_intake(yaml_path: Path) -> ValidationReport:
    """Validate a G0 hotfix intake artifact."""
    issues = []
    
    if not yaml_path.exists():
        return ValidationReport(
            outcome="FAIL",
            issues=[ValidationIssue(
                code="FILE_MISSING",
                artifact="g0-intake",
                location=str(yaml_path),
                message="Intake file does not exist"
            )]
        )
    
    try:
        with yaml_path.open("r") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        return ValidationReport(
            outcome="FAIL",
            issues=[ValidationIssue(
                code="PARSE_ERROR",
                artifact="g0-intake",
                location=str(yaml_path),
                message=f"Failed to parse YAML: {e}"
            )]
        )
    
    if data is None:
        return ValidationReport(
            outcome="FAIL",
            issues=[ValidationIssue(
                code="EMPTY_FILE",
                artifact="g0-intake",
                location=str(yaml_path),
                message="File contains no valid YAML content"
            )]
        )
    
    # Check required fields
    required_fields = [
        "schema_version", "artifact_type", "generated_at", 
        "mode", "task_description", "activation_phrase",
        "risk_assessment", "affected_files", "scope_hash_prefix",
        "human_author", "approval_recorded", "prohibited_actions_verified"
    ]
    
    for field in required_fields:
        if field not in data:
            issues.append(ValidationIssue(
                code="MISSING_FIELD",
                artifact="g0-intake",
                location=field,
                message=f"Required field missing: {field}"
            ))
    
    # Validate mode value
    if "mode" in data and data["mode"] not in ["hotfix", "rescue"]:
        issues.append(ValidationIssue(
            code="INVALID_MODE",
            artifact="g0-intake",
            location="mode",
            message=f"Mode must be 'hotfix' or 'rescue', got: {data['mode']}"
        ))
    
    # Validate risk assessment
    if "risk_assessment" in data and data["risk_assessment"] not in ["low", "medium", "high"]:
        issues.append(ValidationIssue(
            code="INVALID_RISK",
            artifact="g0-intake",
            location="risk_assessment",
            message=f"Risk must be 'low', 'medium', or 'high', got: {data['risk_assessment']}"
        ))
    
    # Validate affected_files is a list
    if "affected_files" in data and not isinstance(data["affected_files"], list):
        issues.append(ValidationIssue(
            code="INVALID_FILES_FORMAT",
            artifact="g0-intake",
            location="affected_files",
            message="affected_files must be a list"
        ))
    
    # Validate scope_hash_prefix length (approximately 16 chars)
    if "scope_hash_prefix" in data:
        prefix = data["scope_hash_prefix"]
        if not isinstance(prefix, str) or len(prefix) < 8:
            issues.append(ValidationIssue(
                code="INVALID_HASH_PREFIX",
                artifact="g0-intake",
                location="scope_hash_prefix",
                message=f"Scope hash prefix too short or invalid: {prefix}"
            ))
    
    # Validate approved_files are not production-data paths
    if "affected_files" in data and isinstance(data["affected_files"], list):
        for filepath in data["affected_files"]:
            if isinstance(filepath, str) and ("production_data/" in filepath or 
                "credential" in filepath.lower() or 
                ".env" in filepath.lower()):
                issues.append(ValidationIssue(
                    code="PROHIBITED_FILE",
                    artifact="g0-intake",
                    location=f"affected_files->{filepath}",
                    message=f"Prohibited file type detected: {filepath}"
                ))
    
    # Generate outcome
    if not issues:
        return ValidationReport(outcome="PASS", issues=[])
    else:
        return ValidationReport(outcome="FAIL", issues=issues)


def main():
    parser = argparse.ArgumentParser(description="Validate hotfix/rescue G0 intake")
    parser.add_argument("--path", default=".gwc/g0-intake.yaml", help="Path to intake YAML")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    path = Path(args.path)
    
    report = validate_intake(path)
    
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        sys.exit(0 if report.valid else 1)
    else:
        print(f"Outcome: {report.outcome}")
        print(f"Valid: {report.valid}")
        for issue in report.issues:
            print(f"  - [{issue.code}] {issue.location}: {issue.message}")
        sys.exit(0 if report.valid else 1)


if __name__ == "__main__":
    main()
