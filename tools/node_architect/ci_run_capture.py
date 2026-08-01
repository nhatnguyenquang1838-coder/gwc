"""Replay-safe CI run capture helper for repo_delivery.ci-run-capture."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Mapping

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class CiRunCaptureDecision:
    outcome: str
    reason_codes: list[str]
    repository: str
    branch: str
    head_sha: str
    required_workflows: list[str]
    captured_runs: list[dict[str, Any]]
    missing_workflows: list[str]
    decision_digest: str
    merge_authority_granted: bool = False
    deployment_authority_granted: bool = False
    production_authority_granted: bool = False


def _digest(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _is_sha(value: object) -> bool:
    return isinstance(value, str) and bool(_SHA_RE.fullmatch(value))


def _latest_exact_run(runs: list[Mapping[str, Any]], workflow: str, head_sha: str) -> Mapping[str, Any] | None:
    exact = [run for run in runs if run.get("name") == workflow and run.get("head_sha") == head_sha]
    if not exact:
        return None
    return sorted(exact, key=lambda run: (int(run.get("attempt", 1) or 1), int(run.get("run_id", 0) or 0)), reverse=True)[0]


def decide_ci_run_capture(evidence: Mapping[str, Any]) -> dict[str, Any]:
    repository = str(evidence.get("repository", ""))
    branch = str(evidence.get("branch", ""))
    head_sha = str(evidence.get("head_sha", ""))
    connector_status = evidence.get("connector_status", "available")
    required = list(evidence.get("required_workflows") or [])
    runs = [run for run in list(evidence.get("runs") or []) if isinstance(run, Mapping)]
    reasons: list[str] = []
    captured: list[dict[str, Any]] = []
    missing: list[str] = []

    if not repository:
        reasons.append("REPOSITORY_MISSING")
    if not branch:
        reasons.append("BRANCH_MISSING")
    if not _is_sha(head_sha):
        reasons.append("INVALID_HEAD_SHA")
    if connector_status != "available":
        reasons.append("CI_READBACK_UNAVAILABLE")
    if not required:
        reasons.append("REQUIRED_WORKFLOWS_MISSING")

    outcome = "PASSED"
    for workflow in required:
        run = _latest_exact_run(runs, str(workflow), head_sha)
        if run is None:
            missing.append(str(workflow))
            continue
        captured.append({
            "name": run.get("name"),
            "run_id": run.get("run_id"),
            "attempt": run.get("attempt", 1),
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "head_sha": run.get("head_sha"),
        })
        if run.get("status") != "completed":
            outcome = "PENDING"
            reasons.append("CI_NON_TERMINAL")
        elif run.get("conclusion") == "success":
            pass
        elif run.get("conclusion") == "cancelled":
            outcome = "CANCELLED"
            reasons.append("CI_CANCELLED")
        else:
            outcome = "FAILED"
            reasons.append("CI_FAILED")

    if missing:
        outcome = "UNAVAILABLE" if outcome == "PASSED" else outcome
        reasons.append("CI_RUN_MISSING")
    if "CI_READBACK_UNAVAILABLE" in reasons:
        outcome = "UNAVAILABLE"
    if any(run.get("head_sha") != head_sha for run in runs):
        reasons.append("STALE_HEAD_RUNS_IGNORED")
    if any(reason in reasons for reason in ["REPOSITORY_MISSING", "BRANCH_MISSING", "INVALID_HEAD_SHA", "REQUIRED_WORKFLOWS_MISSING"]):
        outcome = "BLOCKED"

    payload = {
        "repository": repository,
        "branch": branch,
        "head_sha": head_sha,
        "required": sorted(map(str, required)),
        "captured": captured,
        "missing": sorted(missing),
        "outcome": outcome,
    }
    return asdict(CiRunCaptureDecision(
        outcome=outcome,
        reason_codes=sorted(set(reasons)) or ["CI_EXACT_HEAD_PASSED"],
        repository=repository,
        branch=branch,
        head_sha=head_sha,
        required_workflows=sorted(map(str, required)),
        captured_runs=captured,
        missing_workflows=sorted(missing),
        decision_digest=_digest(payload),
    ))
