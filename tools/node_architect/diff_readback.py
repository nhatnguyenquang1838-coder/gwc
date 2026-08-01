"""Replay-safe diff readback decision helper for repo_delivery.diff-readback."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from fnmatch import fnmatch
import hashlib
import json
import re
from typing import Any, Mapping

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class DiffReadbackDecision:
    outcome: str
    reason_codes: list[str]
    repository: str
    base_sha: str
    head_sha: str
    branch: str
    changed_paths: list[str]
    additions: int
    deletions: int
    decision_digest: str
    merge_authority_granted: bool = False
    deployment_authority_granted: bool = False
    production_authority_granted: bool = False


def _digest(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _is_sha(value: object) -> bool:
    return isinstance(value, str) and bool(_SHA_RE.fullmatch(value))


def _path_allowed(path: str, approved_paths: list[str]) -> bool:
    for pattern in approved_paths:
        if pattern.endswith("/**") and path.startswith(pattern[:-3] + "/"):
            return True
        if "*" in pattern and fnmatch(path, pattern):
            return True
        if path == pattern:
            return True
    return False


def decide_diff_readback(evidence: Mapping[str, Any]) -> dict[str, Any]:
    repository = str(evidence.get("repository", ""))
    base_sha = str(evidence.get("base_sha", ""))
    head_sha = str(evidence.get("head_sha", ""))
    branch = str(evidence.get("branch", ""))
    connector_status = evidence.get("connector_status", "available")
    compare_status = evidence.get("compare_status")
    approved_paths = list(evidence.get("approved_paths") or [])
    changed_files = list(evidence.get("changed_files") or [])
    reasons: list[str] = []
    outcome = "PASS"

    if not repository:
        reasons.append("REPOSITORY_MISSING")
    if not _is_sha(base_sha):
        reasons.append("INVALID_BASE_SHA")
    if not _is_sha(head_sha):
        reasons.append("INVALID_HEAD_SHA")
    if not branch:
        reasons.append("BRANCH_MISSING")
    if connector_status != "available":
        reasons.append("READBACK_UNAVAILABLE")
        outcome = "HUMAN_REQUIRED"
    if compare_status not in {"ahead", "identical"}:
        reasons.append("COMPARE_STATUS_INVALID")
    if int(evidence.get("behind_by", 0) or 0) != 0:
        reasons.append("BASE_DRIFT")
    if int(evidence.get("ahead_by", 0) or 0) < 1:
        reasons.append("NO_BRANCH_DELTA")
    if not approved_paths:
        reasons.append("APPROVED_SCOPE_MISSING")
    if not changed_files:
        reasons.append("CHANGED_FILES_MISSING")

    paths: list[str] = []
    additions = 0
    deletions = 0
    for entry in changed_files:
        if not isinstance(entry, Mapping):
            reasons.append("INVALID_FILE_ENTRY")
            continue
        path = str(entry.get("filename") or entry.get("path") or "")
        if not path:
            reasons.append("EMPTY_CHANGED_PATH")
            continue
        paths.append(path)
        additions += int(entry.get("additions", 0) or 0)
        deletions += int(entry.get("deletions", 0) or 0)
        if not _path_allowed(path, approved_paths):
            reasons.append("OUT_OF_SCOPE_PATH")
        if entry.get("status") == "removed":
            reasons.append("DELETE_NOT_APPROVED")

    if reasons and outcome != "HUMAN_REQUIRED":
        outcome = "BLOCKED"

    digest_payload = {
        "repository": repository,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "branch": branch,
        "paths": sorted(paths),
        "outcome": outcome,
        "reasons": sorted(set(reasons)),
    }
    return asdict(DiffReadbackDecision(
        outcome=outcome,
        reason_codes=sorted(set(reasons)) or ["DIFF_READBACK_OK"],
        repository=repository,
        base_sha=base_sha,
        head_sha=head_sha,
        branch=branch,
        changed_paths=sorted(paths),
        additions=additions,
        deletions=deletions,
        decision_digest=_digest(digest_payload),
    ))
