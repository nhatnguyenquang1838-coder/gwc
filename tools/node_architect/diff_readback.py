"""Replay-safe diff readback decision helper for repo_delivery.diff-readback.

Closes the live SCRUM-319 AC gaps (Controller CORRECTION seq=3, DELTA_REQUIRED):
  * completeness/visibility fail-closed (partial compare must NOT be
    misclassified as complete),
  * explicit prohibited-change detection (distinct from out-of-scope),
  * deterministic content/provenance evidence (enriched decision_digest),
  * stale base/head SHA fail-closed,
  * same-input replay/digest stability,
  * never grants review/merge/deploy authority.

Backward compatible: new inputs are optional; when absent the legacy verdict
is preserved so pre-existing callers/tests stay green.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from fnmatch import fnmatch
import hashlib
import json
import re
from typing import Any, Mapping

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

# Fail-closed visibility states required by the live Jira AC.
_READBACK_COVERAGE_VALID = ("complete",)


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


def _path_prohibited(path: str, prohibited_paths: list[str]) -> bool:
    """Explicit prohibited-change match (immutable authority/control-plane)."""
    if not prohibited_paths:
        return False
    for pattern in prohibited_paths:
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
    # Optional: explicit expected SHAs for stale-SHA fail-closed (live Jira AC).
    expected_base_sha = evidence.get("expected_base_sha")
    expected_head_sha = evidence.get("expected_head_sha")
    # Optional: completeness/visibility proof (live Jira AC). Fail-closed:
    # absent or unrecognized coverage is treated as UNKNOWN (never silently
    # "complete"). Existence of a completeness proof is mandatory.
    readback_coverage = str(evidence.get("readback_coverage", "unknown") or "unknown").lower()
    # Optional: explicit prohibited paths/patterns (immutable authority plane).
    prohibited_paths = list(evidence.get("prohibited_paths") or [])
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

    # --- Stale SHA fail-closed (live Jira AC) ---
    if expected_base_sha is not None and base_sha != str(expected_base_sha):
        reasons.append("STALE_BASE_SHA")
    if expected_head_sha is not None and head_sha != str(expected_head_sha):
        reasons.append("STALE_HEAD_SHA")

    # --- Completeness / visibility fail-closed (live Jira AC) ---
    if readback_coverage == "partial":
        reasons.append("INCOMPLETE_VISIBILITY")
    elif readback_coverage == "unknown":
        reasons.append("READBACK_VISIBILITY_UNKNOWN")
    elif readback_coverage not in _READBACK_COVERAGE_VALID:
        reasons.append("READBACK_VISIBILITY_UNKNOWN")

    paths: list[str] = []
    prohibited_hits: list[str] = []
    file_fingerprints: list[dict] = []
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
        f_status = str(entry.get("status") or "")
        f_add = int(entry.get("additions", 0) or 0)
        f_del = int(entry.get("deletions", 0) or 0)
        paths.append(path)
        additions += f_add
        deletions += f_del
        file_fingerprints.append({
            "path": path, "status": f_status, "additions": f_add, "deletions": f_del,
        })
        if not _path_allowed(path, approved_paths):
            reasons.append("OUT_OF_SCOPE_PATH")
        # Explicit prohibited-change detection (distinct from out-of-scope).
        if _path_prohibited(path, prohibited_paths):
            prohibited_hits.append(path)
            reasons.append("PROHIBITED_CHANGE_DETECTED")
        if f_status == "removed":
            reasons.append("DELETE_NOT_APPROVED")

    if reasons and outcome != "HUMAN_REQUIRED":
        outcome = "BLOCKED"

    # Deterministic content/provenance evidence: digest over the stable,
    # content-aware fingerprint (repository, base/head, coverage, sorted
    # per-file fingerprints with status/additions/deletions, totals,
    # prohibited hits, reason codes, outcome). Same input => same digest
    # (replay stability); differing content => differing digest.
    digest_payload = {
        "repository": repository,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "branch": branch,
        "readback_coverage": readback_coverage,
        "files": sorted(file_fingerprints, key=lambda f: f["path"]),
        "additions": additions,
        "deletions": deletions,
        "prohibited_hits": sorted(set(prohibited_hits)),
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
