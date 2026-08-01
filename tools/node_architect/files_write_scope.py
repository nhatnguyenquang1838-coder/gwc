#!/usr/bin/env python3
"""Render a bounded write-scope artifact for intake_context.files-write-scope."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

NODE_ID = "intake_context.files-write-scope"
ARTIFACT_TYPE = "bounded-write-scope"
DEFAULT_GATE = "G0_CONTEXT"
DEFAULT_AUTHORITY = "read_only"
DEFAULT_ENTRY_GUARDS = [DEFAULT_GATE, DEFAULT_AUTHORITY]
DEFAULT_CONSTRAINTS = [
    "Write scope must be repo-relative and bounded to approved task files only.",
    "Write scope must exclude protected-branch, merge, deploy, release, credential, migration, and production-data actions.",
    "Write scope must fail closed when the candidate write set is empty or ambiguous.",
]
DEFAULT_EXCLUSIONS = [
    "Direct push to protected branches.",
    "Force push, branch deletion, or PR base changes.",
    "Merge, auto-merge, deploy, release, production config, credentials, secrets, migration, and production data.",
]
DEFAULT_EXCLUDED_ACTIONS = [
    "direct_push_main",
    "force_push",
    "delete_branch",
    "change_pr_base",
    "merge",
    "auto_merge",
    "deploy",
    "release",
    "production_config",
    "credentials",
    "secrets",
    "migration",
    "production_data",
]
DEFAULT_REASON_CODES = {
    "ACCEPTED": "Required write scope rendered successfully.",
    "EMPTY_SCOPE": "No bounded write paths were available for the task.",
    "PROHIBITED_ACTION": "Candidate write scope includes a prohibited action or target.",
    "MALFORMED_INPUT": "Write scope inputs are invalid or ambiguous.",
    "SCOPE_DRIFT": "Requested write scope exceeds the bounded task envelope.",
}
REPO_PATTERN = re.compile(r"^[^/\s]+/[^/\s]+$")
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def _require_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _canonical_paths(values: Any, label: str) -> list[str]:
    if not isinstance(values, list):
        raise ValueError(f"{label} must be a list of strings")
    canonical: list[str] = []
    seen: set[str] = set()
    for raw in values:
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError(f"{label} entries must be non-empty strings")
        value = raw.strip()
        if value.startswith(("/", "\\")) or "\\" in value or ":" in value:
            raise ValueError(f"{label} entries must be repo-relative paths")
        if any(part in {"", ".."} for part in value.split("/")):
            raise ValueError(f"{label} entries must not contain traversal segments")
        if value not in seen:
            seen.add(value)
            canonical.append(value)
    if not canonical:
        raise ValueError(f"{label} must not be empty")
    return canonical


def _canonical_list(payload: dict[str, Any], key: str, default: list[str]) -> list[str]:
    if key not in payload or payload[key] is None:
        return list(default)
    return _canonical_paths(payload[key], key)


def _canonical_reason_codes(payload: dict[str, Any]) -> dict[str, str]:
    if "reason_codes" not in payload or payload["reason_codes"] is None:
        return dict(DEFAULT_REASON_CODES)
    reason_codes = payload["reason_codes"]
    if not isinstance(reason_codes, dict):
        raise ValueError("reason_codes must be an object when present")
    if set(reason_codes) != set(DEFAULT_REASON_CODES):
        raise ValueError(
            "reason_codes must define ACCEPTED, EMPTY_SCOPE, PROHIBITED_ACTION, MALFORMED_INPUT, and SCOPE_DRIFT"
        )
    canonical: dict[str, str] = {}
    for key, value in reason_codes.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("reason_codes keys must be non-empty strings")
        if not isinstance(value, str) or not value.strip():
            raise ValueError("reason_codes values must be non-empty strings")
        canonical[key] = value.strip()
    return canonical


def render_files_write_scope(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    files_write = payload.get("files_write")
    if files_write is None:
        files_write = payload.get("write_candidates", [])
    canonical_files = _canonical_paths(files_write, "files_write")
    repository = _require_text(payload, "repository")
    if not REPO_PATTERN.fullmatch(repository):
        raise ValueError("repository must be in owner/name format")
    base_sha = _require_text(payload, "base_sha")
    if not SHA_PATTERN.fullmatch(base_sha):
        raise ValueError("base_sha must be a 40-character lowercase hex string")

    return {
        "schema_version": "1.0",
        "artifact_type": ARTIFACT_TYPE,
        "node_id": NODE_ID,
        "task_id": _require_text(payload, "task_id"),
        "repository": repository,
        "base_sha": base_sha,
        "branch": _require_text(payload, "branch"),
        "gate": DEFAULT_GATE,
        "authority_boundary": DEFAULT_AUTHORITY,
        "files_write": canonical_files,
        "constraints": _canonical_list(payload, "constraints", DEFAULT_CONSTRAINTS),
        "exclusions": _canonical_list(payload, "exclusions", DEFAULT_EXCLUSIONS),
        "excluded_actions": _canonical_list(payload, "excluded_actions", DEFAULT_EXCLUDED_ACTIONS),
        "entry_guards": _canonical_list(payload, "entry_guards", DEFAULT_ENTRY_GUARDS),
        "reason_codes": _canonical_reason_codes(payload),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Path to a JSON payload.")
    parser.add_argument("--output", type=Path, help="Optional output path for the rendered JSON.")
    args = parser.parse_args(argv)

    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        rendered = render_files_write_scope(payload)
        encoded = json.dumps(rendered, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.write_text(encoded, encoding="utf-8")
        else:
            sys.stdout.write(encoded)
    except Exception as exc:  # noqa: BLE001 - CLI should report all validation failures.
        sys.stderr.write(f"ERROR: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
