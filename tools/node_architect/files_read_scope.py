#!/usr/bin/env python3
"""Render a bounded read-scope artifact for intake_context.files-read-scope."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

NODE_ID = "intake_context.files-read-scope"
ARTIFACT_TYPE = "bounded-read-scope"
DEFAULT_GATE = "G0_CONTEXT"
DEFAULT_AUTHORITY = "read_only"
DEFAULT_ENTRY_GUARDS = [DEFAULT_GATE, DEFAULT_AUTHORITY]
DEFAULT_CONSTRAINTS = [
    "Read scope must be derived from verified governance and task-specific inputs only.",
    "Read scope must remain read-only and fail closed on missing evidence.",
    "Read paths must stay within the repository boundary.",
]
DEFAULT_EXCLUSIONS = [
    "Production runtime behavior.",
    "Merge, deploy, release, or production-data operations.",
    "Write paths and destructive side effects.",
]
DEFAULT_REASON_CODES = {
    "ACCEPTED": "Required read scope rendered successfully.",
    "MISSING_EVIDENCE": "Required read inputs are missing or incomplete.",
    "MALFORMED_INPUT": "Read scope inputs are invalid or ambiguous.",
    "SCOPE_DRIFT": "Requested read scope exceeds the bounded task envelope.",
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
        raise ValueError("reason_codes must define ACCEPTED, MISSING_EVIDENCE, MALFORMED_INPUT, and SCOPE_DRIFT")
    canonical: dict[str, str] = {}
    for key, value in reason_codes.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("reason_codes keys must be non-empty strings")
        if not isinstance(value, str) or not value.strip():
            raise ValueError("reason_codes values must be non-empty strings")
        canonical[key] = value.strip()
    return canonical


def render_files_read_scope(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    files_read = payload.get("files_read")
    if files_read is None:
        files_read = []
        governance_reads = payload.get("governance_reads")
        if governance_reads is not None:
            files_read.extend(_canonical_paths(governance_reads, "governance_reads"))
        task_reads = payload.get("task_reads")
        if task_reads is not None:
            files_read.extend(_canonical_paths(task_reads, "task_reads"))
    canonical_files = _canonical_paths(files_read, "files_read")
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
        "files_read": canonical_files,
        "constraints": _canonical_list(payload, "constraints", DEFAULT_CONSTRAINTS),
        "exclusions": _canonical_list(payload, "exclusions", DEFAULT_EXCLUSIONS),
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
        rendered = render_files_read_scope(payload)
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
