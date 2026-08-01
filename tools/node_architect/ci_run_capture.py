"""Replay-safe CI run capture helper for repo_delivery.ci-run-capture.

This module preserves the original SCRUM-198 replay API while adding the B2
pure decision helper used by repo_delivery.ci-run-capture maturity work.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Mapping

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
TERMINAL_SUCCESS = {"success", "passed"}
TERMINAL_FAILURE = {"failure", "cancelled", "timed_out", "action_required", "failed", "error"}
NON_TERMINAL = {"queued", "waiting", "requested", "in_progress", "pending"}


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


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest_payload(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _digest(payload: Mapping[str, Any]) -> str:
    return digest_payload(payload)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _is_sha(value: object) -> bool:
    return isinstance(value, str) and bool(_SHA_RE.fullmatch(value))


def _run_conclusion(run: Mapping[str, Any]) -> str | None:
    conclusion = run.get("conclusion")
    if conclusion is not None:
        return str(conclusion).lower()
    state = run.get("status")
    return str(state).lower() if state is not None else None


def classify_provider_payload(head_sha: str, payload: Mapping[str, Any]) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], bool]:
    runs = list(payload.get("workflow_runs") or payload.get("runs") or [])
    statuses = list(payload.get("statuses") or [])
    candidates: list[dict[str, Any]] = []

    for run in runs:
        if not isinstance(run, Mapping):
            continue
        candidate_sha = run.get("head_sha") or run.get("headSha") or run.get("sha")
        candidates.append({
            "source": "workflow_run",
            "id": run.get("id") or run.get("run_id"),
            "name": run.get("name") or run.get("workflow") or run.get("workflow_name"),
            "head_sha": candidate_sha,
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "url": run.get("html_url") or run.get("url"),
        })
    for status in statuses:
        if not isinstance(status, Mapping):
            continue
        candidate_sha = status.get("sha") or payload.get("sha") or head_sha
        candidates.append({
            "source": "combined_status",
            "id": status.get("id") or status.get("context"),
            "name": status.get("context") or status.get("name"),
            "head_sha": candidate_sha,
            "status": status.get("state"),
            "conclusion": status.get("conclusion") or status.get("state"),
            "url": status.get("target_url") or status.get("url"),
        })

    selected = [item for item in candidates if item.get("head_sha") == head_sha]
    rejected = [
        {**item, "reason": "sha_mismatch" if item.get("head_sha") else "missing_head_sha"}
        for item in candidates
        if item.get("head_sha") != head_sha
    ]
    if not candidates:
        return "UNAVAILABLE", [], [], False
    if not selected:
        return "SHA_MISMATCH", [], rejected, False

    conclusions = {_run_conclusion(item) for item in selected}
    conclusions.discard(None)
    if any(item in TERMINAL_FAILURE for item in conclusions):
        return "FAILED", selected, rejected, False
    if selected and conclusions and all(item in TERMINAL_SUCCESS for item in conclusions):
        return "PASSED", selected, rejected, False
    if any(item in NON_TERMINAL for item in conclusions):
        return "PENDING", selected, rejected, True
    return "UNAVAILABLE", selected, rejected, False


def capture_ci_observation(
    *,
    task_id: str,
    repository: str,
    branch: str,
    base_sha: str,
    head_sha: str,
    scope_hash: str,
    provider_payload: Mapping[str, Any],
    observed_at: str | None = None,
) -> dict[str, Any]:
    classification, selected, rejected, checkpoint_required = classify_provider_payload(head_sha, provider_payload)
    observation = {
        "schema_version": "1.0",
        "artifact_type": "ci-observation",
        "task_id": task_id,
        "repository": repository,
        "branch": branch,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "scope_hash": scope_hash,
        "observed_at": observed_at or _now(),
        "classification": classification,
        "selected_runs": selected,
        "rejected_candidates": rejected,
        "checkpoint_required": checkpoint_required,
        "provider_payload_digest": digest_payload(provider_payload),
    }
    observation["observation_digest"] = digest_payload({k: v for k, v in observation.items() if k != "observation_digest"})
    return observation


def is_replay_equivalent(first: Mapping[str, Any], second: Mapping[str, Any]) -> bool:
    def stable(payload: Mapping[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in payload.items() if k not in {"observed_at", "observation_digest"}}

    return digest_payload(stable(first)) == digest_payload(stable(second))


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
