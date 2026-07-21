#!/usr/bin/env python3
"""Validate Kiro/local-agent execution package boundaries.

This validator intentionally uses only the Python standard library so Kiro and
other local agents can run it before repository mutation.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ALLOWED_COMMAND_CATEGORIES = {
    "read_context",
    "create_worktree",
    "modify_scoped_files",
    "run_validation",
    "readback_diff",
    "prepare_draft_pr_handoff",
}

FORBIDDEN_COMMAND_CATEGORIES = {
    "merge",
    "enable_auto_merge",
    "deploy",
    "release",
    "production_config",
    "production_data",
    "secret_or_credential",
    "migration",
    "direct_push_main",
    "force_push",
    "delete_branch",
    "rewrite_history",
    "change_pr_base",
}

REQUIRED_TOP_LEVEL = {
    "schema_version",
    "package_id",
    "package_type",
    "task",
    "checkpoint",
    "repository",
    "authority",
    "scope",
    "commands",
    "validation",
    "reporting",
    "prohibited_actions",
}

REQUIRED_REPORT_FIELDS = {
    "package_id",
    "task_id",
    "checkpoint_id",
    "repository",
    "base_sha",
    "branch",
    "files_read_actual",
    "files_write_actual",
    "changed_files",
    "commands_executed",
    "validation_performed",
    "validation_skipped",
    "evidence",
    "limitations",
    "scope_drift",
    "prohibited_action_detected",
    "next_gate",
}


class ValidationError(Exception):
    """Raised for invalid packages."""


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def as_set(value: Any, field: str) -> set[str]:
    ensure(isinstance(value, list), f"{field} must be a list")
    ensure(all(isinstance(item, str) and item for item in value), f"{field} must contain non-empty strings")
    return set(value)


def validate_package(package: dict[str, Any]) -> list[str]:
    findings: list[str] = []

    ensure(isinstance(package, dict), "package must be a JSON object")
    missing = sorted(REQUIRED_TOP_LEVEL - set(package))
    ensure(not missing, f"missing top-level fields: {', '.join(missing)}")

    ensure(package["schema_version"] == "0.1", "schema_version must be 0.1")
    ensure(package["package_type"] == "kiro_local_agent_execution_package", "invalid package_type")

    task = package["task"]
    repository = package["repository"]
    checkpoint = package["checkpoint"]
    authority = package["authority"]
    scope = package["scope"]

    for field, obj in {
        "task": task,
        "repository": repository,
        "checkpoint": checkpoint,
        "authority": authority,
        "scope": scope,
    }.items():
        ensure(isinstance(obj, dict), f"{field} must be an object")

    ensure(task.get("id"), "task.id is required")
    ensure(checkpoint.get("checkpoint_id"), "checkpoint.checkpoint_id is required")
    ensure(repository.get("full_name"), "repository.full_name is required")
    ensure(repository.get("base_branch"), "repository.base_branch is required")
    ensure(repository.get("base_sha"), "repository.base_sha is required")
    ensure(repository.get("working_branch"), "repository.working_branch is required")
    ensure(repository.get("working_branch") != repository.get("base_branch"), "working branch must differ from base branch")

    ensure(authority.get("gate") == "G2", "authority.gate must be G2 for repository mutation packages")
    ensure(authority.get("approval_request_id"), "authority.approval_request_id is required")
    scope_hash = authority.get("scope_hash_16")
    ensure(isinstance(scope_hash, str) and len(scope_hash) == 16, "authority.scope_hash_16 must be 16 chars")
    ensure(authority.get("human_approval_required") is False, "active G2 approval must already be captured")

    files_read = as_set(scope.get("files_read"), "scope.files_read")
    files_write = as_set(scope.get("files_write"), "scope.files_write")
    ensure(files_write, "scope.files_write must not be empty")

    commands = package["commands"]
    ensure(isinstance(commands, list) and commands, "commands must be a non-empty list")
    seen_categories = set()

    for index, command in enumerate(commands):
        ensure(isinstance(command, dict), f"commands[{index}] must be an object")
        category = command.get("category")
        ensure(category in ALLOWED_COMMAND_CATEGORIES, f"commands[{index}].category is not allowed: {category}")
        ensure(category not in FORBIDDEN_COMMAND_CATEGORIES, f"commands[{index}].category is forbidden: {category}")
        seen_categories.add(category)
        touches = as_set(command.get("touches", []), f"commands[{index}].touches")
        if category == "modify_scoped_files":
            ensure(touches, "modify_scoped_files command must declare touched files")
            outside = sorted(touches - files_write)
            ensure(not outside, f"modify command touches files outside scope.files_write: {', '.join(outside)}")
        elif touches:
            outside_known = sorted(touches - files_read - files_write)
            ensure(not outside_known, f"command touches files outside files_read/files_write: {', '.join(outside_known)}")

    ensure("modify_scoped_files" in seen_categories, "package must include modify_scoped_files command")
    ensure("run_validation" in seen_categories, "package must include run_validation command")
    ensure("readback_diff" in seen_categories, "package must include readback_diff command")

    prohibited_actions = as_set(package["prohibited_actions"], "prohibited_actions")
    missing_prohibited = sorted(FORBIDDEN_COMMAND_CATEGORIES - prohibited_actions)
    ensure(not missing_prohibited, f"prohibited_actions missing: {', '.join(missing_prohibited)}")

    validation = package["validation"]
    ensure(isinstance(validation, dict), "validation must be an object")
    required_validation = as_set(validation.get("required"), "validation.required")
    ensure(required_validation, "validation.required must not be empty")

    reporting = package["reporting"]
    ensure(isinstance(reporting, dict), "reporting must be an object")
    required_report_fields = as_set(reporting.get("required_fields"), "reporting.required_fields")
    missing_report_fields = sorted(REQUIRED_REPORT_FIELDS - required_report_fields)
    ensure(not missing_report_fields, f"reporting.required_fields missing: {', '.join(missing_report_fields)}")

    findings.append("package_valid")
    return findings


def validate_report(package: dict[str, Any], report: dict[str, Any]) -> list[str]:
    findings = validate_package(package)
    ensure(isinstance(report, dict), "report must be a JSON object")
    missing = sorted(REQUIRED_REPORT_FIELDS - set(report))
    ensure(not missing, f"report missing fields: {', '.join(missing)}")

    ensure(report["package_id"] == package["package_id"], "report.package_id does not match package")
    ensure(report["task_id"] == package["task"]["id"], "report.task_id does not match package")
    ensure(report["checkpoint_id"] == package["checkpoint"]["checkpoint_id"], "report.checkpoint_id does not match package")
    ensure(report["repository"] == package["repository"]["full_name"], "report.repository does not match package")
    ensure(report["base_sha"] == package["repository"]["base_sha"], "report.base_sha does not match package")
    ensure(report["branch"] == package["repository"]["working_branch"], "report.branch does not match package")

    changed_files = as_set(report["changed_files"], "report.changed_files")
    files_write = as_set(package["scope"]["files_write"], "package.scope.files_write")
    outside = sorted(changed_files - files_write)
    ensure(not outside, f"report.changed_files outside package scope: {', '.join(outside)}")
    ensure(report["scope_drift"] in {"NONE", "DETECTED"}, "report.scope_drift invalid")
    ensure(report["prohibited_action_detected"] is False, "report detected prohibited action")

    findings.append("report_valid")
    return findings


def result(status: str, findings: list[str], error: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": status, "findings": findings}
    if error:
        payload["error"] = error
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a Kiro/local-agent execution package.")
    parser.add_argument("package", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    try:
        package = load_json(args.package)
        if args.report:
            findings = validate_report(package, load_json(args.report))
        else:
            findings = validate_package(package)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        print(json.dumps(result("FAIL", [], str(exc)), sort_keys=True, separators=(",", ":")))
        return 1

    print(json.dumps(result("PASS", findings), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
