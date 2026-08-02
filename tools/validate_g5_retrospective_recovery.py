#!/usr/bin/env python3
"""Validate retrospective G5 recovery evidence.

This validator intentionally does not mint normal G4 merge authority. It only
accepts a post-merge evidence-recovery comment that binds the original human
approval, merged PR, merge commit, and failed post-merge run while explicitly
blocking new merge, manual G5, deployment, and G6 authority.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
APPROVAL_RE = re.compile(
    r"^APPROVE (?:G4_MERGE|G4) "
    r"(?P<approval_id>[A-Za-z0-9._:-]+) "
    r"(?P<approval_prefix>[0-9a-f]{16}) "
    r"(?P<expires_at>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)$",
    re.MULTILINE,
)


def _parse_utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"timestamp is not UTC Z format: {value!r}")
    return datetime.fromisoformat(value[:-1] + "+00:00").astimezone(timezone.utc)


def _first(pattern: str, body: str, label: str) -> str:
    match = re.search(pattern, body, flags=re.MULTILINE)
    if not match:
        raise ValueError(f"missing {label}")
    return match.group(1).strip()


def validate(candidate: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    body = str(candidate.get("comment_body") or "")

    if "RETROSPECTIVE G5 RECOVERY EVIDENCE" not in body:
        errors.append("comment is not marked as retrospective G5 recovery evidence")

    command = APPROVAL_RE.search(body)
    if not command:
        errors.append("missing quoted original G4 approval command")

    pr_number = candidate.get("pr_number")
    if not isinstance(pr_number, int):
        errors.append("pr_number must be an integer")

    if candidate.get("pr_merged") is not True:
        errors.append("PR must already be merged for retrospective G5 recovery")

    head_sha = str(candidate.get("pr_head_sha") or "")
    if not HEX40_RE.fullmatch(head_sha):
        errors.append("pr_head_sha must be a full 40-character lowercase SHA")

    merge_sha = str(candidate.get("merge_commit_sha") or "")
    if not HEX40_RE.fullmatch(merge_sha):
        errors.append("merge_commit_sha must be a full 40-character lowercase SHA")

    permission = str(candidate.get("comment_author_permission") or "")
    if permission not in {"admin", "maintain", "write"}:
        errors.append(f"comment author lacks recovery authority: {permission or 'unknown'}")

    if candidate.get("new_merge_authority_inferred") is not False:
        errors.append("recovery must not infer new merge authority")
    if candidate.get("manual_g5_action_authorized") is not False:
        errors.append("recovery must not authorize manual G5 action")
    if candidate.get("g6_authorized") is not False:
        errors.append("recovery must not authorize G6")

    lowered = body.lower()
    required_phrases = [
        "retrospective evidence-recovery",
        "not backdated g4 authority",
        "does not authorize another merge",
        "manual g5 action",
        "g6 action",
    ]
    for phrase in required_phrases:
        if phrase not in lowered:
            errors.append(f"recovery comment must explicitly contain: {phrase}")

    bound_pr = approved_head = bound_merge = failed_run_id = None
    try:
        bound_pr = int(_first(r"^Bound PR:\s*#?(\d+)\s*$", body, "Bound PR"))
        approved_head = _first(r"^Approved head:\s*([0-9a-f]{40})\s*$", body, "Approved head")
        bound_merge = _first(r"^Merge commit:\s*([0-9a-f]{40})\s*$", body, "Merge commit")
        failed_run_id = int(_first(r"^Failed post-merge run:\s*(\d+)\s*$", body, "Failed post-merge run"))
    except ValueError as exc:
        errors.append(str(exc))

    if bound_pr is not None and pr_number is not None and bound_pr != pr_number:
        errors.append(f"Bound PR #{bound_pr} does not match event PR #{pr_number}")
    if approved_head is not None and head_sha and approved_head != head_sha:
        errors.append("Approved head does not match merged PR head")
    if bound_merge is not None and merge_sha and bound_merge != merge_sha:
        errors.append("Merge commit does not match PR merge_commit_sha")

    merged_at = None
    if candidate.get("merged_at"):
        try:
            merged_at = _parse_utc(str(candidate["merged_at"]))
        except ValueError as exc:
            errors.append(str(exc))

    approval_id = approval_prefix = expires_at_raw = None
    if command:
        approval_id = command.group("approval_id")
        approval_prefix = command.group("approval_prefix")
        expires_at_raw = command.group("expires_at")
        if head_sha and approval_prefix != head_sha[:16]:
            errors.append("approval command prefix does not match merged head prefix")
        if merged_at is not None:
            try:
                expires_at = _parse_utc(expires_at_raw)
                if expires_at < merged_at:
                    errors.append("quoted G4 approval expired before the merge event")
            except ValueError as exc:
                errors.append(str(exc))

    if errors:
        raise ValueError("; ".join(errors))

    return {
        "schema_version": "1.0",
        "artifact_type": "g5-retrospective-recovery-evidence",
        "repository": candidate.get("repository"),
        "gate": "G5_STATUS_VERIFY",
        "recovery_mode": "retrospective",
        "approval_id": approval_id,
        "approval_prefix": approval_prefix,
        "source_comment_id": candidate.get("comment_id"),
        "source_comment_url": candidate.get("comment_url"),
        "source_comment_author": candidate.get("comment_author"),
        "source_comment_author_permission": permission,
        "pr_number": pr_number,
        "approved_head_sha": head_sha,
        "merge_commit_sha": merge_sha,
        "merged_at": candidate.get("merged_at"),
        "failed_post_merge_run_id": failed_run_id,
        "original_approval_expires_at": expires_at_raw,
        "normal_g4_authority_minted": False,
        "new_merge_authority_inferred": False,
        "manual_g5_action_authorized": False,
        "g6_authorized": False,
        "recovery_valid": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--write-artifact", type=Path)
    args = parser.parse_args(argv)

    try:
        candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
        artifact = validate(candidate)
    except Exception as exc:  # noqa: BLE001 - validator CLI should print concise failure
        print(f"G5 retrospective recovery validation failed: {exc}", file=sys.stderr)
        return 1

    output = json.dumps(artifact, indent=2, sort_keys=True) + "\n"
    if args.write_artifact:
        args.write_artifact.write_text(output, encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
