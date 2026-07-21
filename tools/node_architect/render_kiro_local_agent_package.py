#!/usr/bin/env python3
"""Render deterministic Kiro/local-agent execution packages.

The renderer accepts a compact plan JSON and expands it into the package shape
validated by validate_kiro_local_agent_package.py.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

FORBIDDEN_COMMAND_CATEGORIES = [
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
]

REPORT_FIELDS = [
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
]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def stable_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def render_package(plan: dict[str, Any]) -> dict[str, Any]:
    files_read = list(plan.get("files_read", []))
    files_write = list(plan.get("files_write", []))
    package_seed = {
        "task_id": plan["task_id"],
        "checkpoint_id": plan["checkpoint_id"],
        "repo": plan["repository"],
        "base_sha": plan["base_sha"],
        "branch": plan["working_branch"],
        "files_write": files_write,
    }
    package_id = plan.get("package_id") or f"kiro-local-{stable_hash(package_seed)}"

    commands = [
        {
            "id": "read-context",
            "category": "read_context",
            "description": "Read declared Files READ and checkpoint artifacts.",
            "touches": list(files_read),
            "expected_output": "Context loaded without widening scope.",
        },
        {
            "id": "modify-scoped-files",
            "category": "modify_scoped_files",
            "description": "Modify only declared Files WRITE.",
            "touches": list(files_write),
            "expected_output": "Repository changes are limited to Files WRITE.",
        },
        {
            "id": "run-validation",
            "category": "run_validation",
            "description": "Run declared local validation commands.",
            "touches": [],
            "expected_output": "Validation report with command output.",
        },
        {
            "id": "readback-diff",
            "category": "readback_diff",
            "description": "Read back diff against protected base SHA.",
            "touches": list(files_write),
            "expected_output": "Scope drift is NONE or execution stops.",
        },
        {
            "id": "prepare-draft-pr-handoff",
            "category": "prepare_draft_pr_handoff",
            "description": "Prepare G3 Draft PR evidence packet.",
            "touches": [],
            "expected_output": "Draft PR handoff without merge authority.",
        },
    ]

    return {
        "schema_version": "0.1",
        "package_id": package_id,
        "package_type": "kiro_local_agent_execution_package",
        "task": {"id": plan["task_id"], "risk": plan.get("risk", "R2")},
        "checkpoint": {
            "checkpoint_id": plan["checkpoint_id"],
            "gate": plan.get("checkpoint_gate", "G2_EXECUTION"),
            "status": plan.get("checkpoint_status", "APPROVED"),
        },
        "repository": {
            "full_name": plan["repository"],
            "base_branch": plan.get("base_branch", "main"),
            "base_sha": plan["base_sha"],
            "working_branch": plan["working_branch"],
        },
        "authority": {
            "gate": "G2",
            "approval_request_id": plan["approval_request_id"],
            "scope_hash_16": plan["scope_hash_16"],
            "issued_at_utc": plan["issued_at_utc"],
            "expires_at_utc": plan["expires_at_utc"],
            "human_approval_required": False,
        },
        "scope": {"files_read": files_read, "files_write": files_write},
        "commands": commands,
        "validation": {"required": list(plan.get("validation_required", ["python -m unittest discover -s tests -p test_*.py"]))},
        "reporting": {"required_fields": REPORT_FIELDS},
        "prohibited_actions": FORBIDDEN_COMMAND_CATEGORIES,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a deterministic Kiro/local-agent package.")
    parser.add_argument("plan", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    try:
        package = render_package(load_json(args.plan))
        encoded = json.dumps(package, sort_keys=True, separators=(",", ":"))
        if args.output:
            args.output.write_text(encoded + "\n", encoding="utf-8")
        else:
            print(encoded)
    except (KeyError, OSError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, sort_keys=True, separators=(",", ":")))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
