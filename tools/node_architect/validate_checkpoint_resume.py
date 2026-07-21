#!/usr/bin/env python3
"""Validate GWC checkpoint + resume token pairs.

This tool intentionally uses only the Python standard library so it can run in
local agents, CI, and constrained connector environments.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GATES = [
    "G0_CONTEXT",
    "G1_ALIGNMENT",
    "G2_EXECUTION",
    "G3_PR",
    "G4_MERGE",
    "G5_DEPLOY",
    "G6_PRODUCTION_DATA",
]

APPROVAL_RE = re.compile(
    r"^APPROVE (G2|G3|G4|G5|G6) [A-Za-z0-9._:-]+ [0-9a-f]{16} [0-9T:\-]+Z$"
)


class ValidationError(ValueError):
    """Raised when checkpoint/resume content is invalid."""


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValidationError(f"{path}: expected JSON object")
    return value


def parse_utc(value: str, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValidationError(f"{field}: expected UTC timestamp ending with Z")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(f"{field}: invalid ISO timestamp") from exc


def require_mapping(value: dict[str, Any], key: str) -> dict[str, Any]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise ValidationError(f"{key}: expected object")
    return item


def require_string(value: dict[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise ValidationError(f"{key}: expected non-empty string")
    return item


def require_list(value: dict[str, Any], key: str) -> list[Any]:
    item = value.get(key)
    if not isinstance(item, list):
        raise ValidationError(f"{key}: expected list")
    return item


def validate_checkpoint(checkpoint: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    try:
        require_string(checkpoint, "checkpoint_id")
        parse_utc(require_string(checkpoint, "created_at_utc"), "created_at_utc")

        task = require_mapping(checkpoint, "task")
        require_string(task, "id")
        require_string(task, "title")
        if task.get("risk_class") not in {"R0", "R1", "R2", "R3"}:
            raise ValidationError("task.risk_class: invalid risk class")

        repo = require_mapping(checkpoint, "repository")
        require_string(repo, "full_name")
        require_string(repo, "base_branch")
        base_sha = require_string(repo, "base_sha")
        if not re.fullmatch(r"[0-9a-f]{40}", base_sha):
            raise ValidationError("repository.base_sha: expected 40 lowercase hex chars")

        gate = require_mapping(checkpoint, "gate")
        if gate.get("current") not in GATES:
            raise ValidationError("gate.current: unknown gate")
        if gate.get("status") not in {"READY", "RUNNING", "PASS", "BLOCKED", "FAILED", "NOT_APPLICABLE"}:
            raise ValidationError("gate.status: invalid status")
        if gate.get("source") not in {"gwc_gate_evidence", "kiro_checkpoint", "git_delivery_evidence"}:
            raise ValidationError("gate.source: invalid source")

        scope = require_mapping(checkpoint, "scope")
        require_list(scope, "files_read")
        require_list(scope, "files_write")
        require_list(scope, "authorized_actions")
        require_list(scope, "excluded_actions")
        if "modify_scoped_files" in scope.get("authorized_actions", []) and not scope.get("files_write"):
            raise ValidationError("scope.files_write: required for scoped write actions")

        validation = require_mapping(checkpoint, "validation")
        require_list(validation, "performed")
        require_list(validation, "skipped")
        require_list(validation, "evidence")

        next_action = require_mapping(checkpoint, "next_action")
        if next_action.get("gate") not in GATES:
            raise ValidationError("next_action.gate: unknown gate")
        require_string(next_action, "action")
        if not isinstance(next_action.get("requires_human_approval"), bool):
            raise ValidationError("next_action.requires_human_approval: expected boolean")

        audit = require_mapping(checkpoint, "audit_projection")
        if audit.get("source_of_truth") is not False:
            raise ValidationError("audit_projection.source_of_truth must be false")
    except ValidationError as exc:
        errors.append(str(exc))
    return errors


def validate_resume_token(
    resume_token: dict[str, Any],
    checkpoint: dict[str, Any],
    *,
    now: datetime | None = None,
) -> list[str]:
    errors: list[str] = []
    now = now or datetime.now(timezone.utc)
    try:
        checkpoint_id = require_string(checkpoint, "checkpoint_id")
        if require_string(resume_token, "checkpoint_id") != checkpoint_id:
            raise ValidationError("resume_token.checkpoint_id does not match checkpoint")

        issued = parse_utc(require_string(resume_token, "issued_at_utc"), "issued_at_utc")
        expires = parse_utc(require_string(resume_token, "expires_at_utc"), "expires_at_utc")
        if expires <= issued:
            raise ValidationError("expires_at_utc must be after issued_at_utc")
        if expires <= now:
            raise ValidationError("resume token is expired")

        if resume_token.get("next_gate") not in GATES:
            raise ValidationError("resume_token.next_gate: unknown gate")
        require_string(resume_token, "next_action")

        requires_approval = resume_token.get("requires_human_approval")
        if not isinstance(requires_approval, bool):
            raise ValidationError("resume_token.requires_human_approval: expected boolean")

        command = resume_token.get("approval_command")
        if requires_approval and not isinstance(command, str):
            raise ValidationError("resume token requiring approval must include approval_command")
        if command is not None and not APPROVAL_RE.fullmatch(command):
            raise ValidationError("approval_command: invalid exact approval command format")

        audit = require_mapping(resume_token, "audit_projection")
        if audit.get("source_of_truth") is not False:
            raise ValidationError("resume audit_projection.source_of_truth must be false")
    except ValidationError as exc:
        errors.append(str(exc))
    return errors


def build_result(errors: list[str]) -> dict[str, Any]:
    return {
        "schema_version": "0.1",
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--resume-token", required=True, type=Path)
    args = parser.parse_args(argv)

    errors: list[str] = []
    try:
        checkpoint = load_json(args.checkpoint)
        resume_token = load_json(args.resume_token)
        errors.extend(validate_checkpoint(checkpoint))
        if not errors:
            errors.extend(validate_resume_token(resume_token, checkpoint))
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        errors.append(str(exc))

    print(json.dumps(build_result(errors), sort_keys=True, separators=(",", ":")))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
