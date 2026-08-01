#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest_payload(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def attach_digest(decision: dict[str, Any]) -> dict[str, Any]:
    decision["decision_digest"] = digest_payload(
        {key: value for key, value in decision.items() if key != "decision_digest"}
    )
    return decision


def _valid_sha(value: str) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(ch in "0123456789abcdef" for ch in value)
    )


def _valid_non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


TERMINAL_FAILURES = {"failure", "cancelled", "timed_out", "action_required", "stale"}
PENDING_STATUSES = {"queued", "pending", "in_progress", "waiting", "requested"}
CONNECTOR_STATUSES = {"CONFIRMED", "EMPTY", "ERROR", "UNSUPPORTED"}


def _parse_utc(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        return datetime.fromisoformat(normalized).astimezone(timezone.utc)
    except ValueError:
        return None


def _valid_run(run: object) -> bool:
    if not isinstance(run, dict):
        return False
    required = ("run_id", "workflow_name", "event", "branch", "head_sha", "status")
    return (
        isinstance(run.get("run_id"), int)
        and not isinstance(run.get("run_id"), bool)
        and run["run_id"] > 0
        and all(_valid_non_empty(run.get(field)) for field in required[1:])
        and _valid_sha(run.get("head_sha"))
        and isinstance(run.get("attempt", 1), int)
        and not isinstance(run.get("attempt", 1), bool)
        and run.get("attempt", 1) > 0
    )


def decide_workflow_run_observability(
    *,
    task_id: str,
    repository: str,
    branch: str,
    base_sha: str,
    head_sha: str,
    expected_event: str,
    expected_branch: str,
    expected_head_sha: str,
    required_workflow_names: list[str],
    connector_status: str,
    exact_filter_applied: bool,
    runs: list[dict[str, Any]],
    slo_completion_seconds: int,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Project exact-SHA workflow evidence while distinguishing visibility gaps."""
    classification = "INVALID_INPUT"
    reason_code = "OBSERVABILITY_INPUT_INVALID"
    observation_complete = False

    identity_invalid = not all(
        _valid_non_empty(value)
        for value in (task_id, repository, branch, expected_event, expected_branch)
    )
    sha_invalid = not all(_valid_sha(value) for value in (base_sha, head_sha, expected_head_sha))
    workflows_invalid = not (
        isinstance(required_workflow_names, list)
        and required_workflow_names
        and all(_valid_non_empty(item) for item in required_workflow_names)
        and len(required_workflow_names) == len(set(required_workflow_names))
    )
    connector_invalid = connector_status not in CONNECTOR_STATUSES or not isinstance(exact_filter_applied, bool)
    runs_invalid = not (
        isinstance(runs, list) and all(_valid_run(run) for run in runs)
    )
    slo_invalid = not (
        isinstance(slo_completion_seconds, int)
        and not isinstance(slo_completion_seconds, bool)
        and slo_completion_seconds > 0
    )

    exact_runs: list[dict[str, Any]] = []
    mismatched_run_count = 0
    selected: dict[str, dict[str, Any]] = {}
    superseded_run_count = 0
    if not runs_invalid:
        for run in runs:
            if (
                run["event"] == expected_event
                and run["branch"] == expected_branch
                and run["head_sha"] == expected_head_sha
                and run["workflow_name"] in required_workflow_names
            ):
                exact_runs.append(run)
            else:
                mismatched_run_count += 1
        for run in exact_runs:
            name = run["workflow_name"]
            current = selected.get(name)
            if current is None or (run.get("attempt", 1), run["run_id"]) > (
                current.get("attempt", 1),
                current["run_id"],
            ):
                if current is not None:
                    superseded_run_count += 1
                selected[name] = run
            else:
                superseded_run_count += 1

    missing_workflow_names = sorted(set(required_workflow_names) - set(selected)) if not workflows_invalid else []
    pending_workflow_names: list[str] = []
    failed_workflow_names: list[str] = []
    successful_workflow_names: list[str] = []
    durations: list[int] = []
    attempts_total = 0

    for name, run in sorted(selected.items()):
        attempts_total += int(run.get("attempt", 1))
        status = run["status"]
        conclusion = run.get("conclusion")
        created = _parse_utc(run.get("created_at"))
        updated = _parse_utc(run.get("updated_at"))
        if created and updated and updated >= created:
            durations.append(int((updated - created).total_seconds()))
        if status in PENDING_STATUSES or status != "completed":
            pending_workflow_names.append(name)
        elif conclusion == "success":
            successful_workflow_names.append(name)
        elif conclusion in TERMINAL_FAILURES or conclusion:
            failed_workflow_names.append(name)
        else:
            failed_workflow_names.append(name)

    max_duration_seconds = max(durations) if durations else None
    slo_breached = (
        max_duration_seconds is not None
        and max_duration_seconds > slo_completion_seconds
    )

    if identity_invalid:
        reason_code = "REQUIRED_IDENTITY_MISSING"
    elif sha_invalid:
        reason_code = "INVALID_OR_MISSING_SHA_BINDING"
    elif workflows_invalid:
        reason_code = "INVALID_REQUIRED_WORKFLOW_SET"
    elif connector_invalid:
        reason_code = "INVALID_CONNECTOR_STATUS"
    elif runs_invalid:
        reason_code = "INVALID_WORKFLOW_RUN_INPUT"
    elif slo_invalid:
        reason_code = "INVALID_SLO_INPUT"
    elif connector_status in {"ERROR", "UNSUPPORTED"}:
        classification = "CONNECTOR_OBSERVABILITY_INCOMPLETE"
        reason_code = "CONNECTOR_CANNOT_CONFIRM_EXACT_RUNS"
    elif connector_status == "EMPTY" and not exact_filter_applied:
        classification = "CONNECTOR_OBSERVABILITY_INCOMPLETE"
        reason_code = "EMPTY_UNFILTERED_CONNECTOR_RESULT"
    elif missing_workflow_names:
        classification = "RUNS_MISSING"
        reason_code = "REQUIRED_EXACT_RUNS_MISSING"
        observation_complete = connector_status in {"CONFIRMED", "EMPTY"} and exact_filter_applied
    elif pending_workflow_names:
        classification = "CI_PENDING"
        reason_code = "EXACT_RUNS_NON_TERMINAL"
        observation_complete = True
    elif failed_workflow_names:
        classification = "CI_FAILED"
        reason_code = "EXACT_RUN_TERMINAL_FAILURE"
        observation_complete = True
    else:
        classification = "SUCCESS"
        reason_code = "EXACT_WORKFLOW_SET_SUCCESSFUL"
        observation_complete = True

    decision = {
        "schema_version": "1.0",
        "artifact_type": "workflow-run-observability-decision",
        "task_id": task_id,
        "repository": repository,
        "branch": branch,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "expected_event": expected_event,
        "expected_branch": expected_branch,
        "expected_head_sha": expected_head_sha,
        "required_workflow_names": sorted(required_workflow_names) if isinstance(required_workflow_names, list) else [],
        "connector_status": connector_status,
        "exact_filter_applied": exact_filter_applied,
        "observed_run_count": len(runs) if isinstance(runs, list) else 0,
        "exact_run_count": len(exact_runs),
        "selected_run_count": len(selected),
        "superseded_run_count": superseded_run_count,
        "mismatched_run_count": mismatched_run_count,
        "missing_workflow_names": missing_workflow_names,
        "pending_workflow_names": sorted(pending_workflow_names),
        "failed_workflow_names": sorted(failed_workflow_names),
        "successful_workflow_names": sorted(successful_workflow_names),
        "slo_ready_metrics": {
            "attempts_total": attempts_total,
            "max_duration_seconds": max_duration_seconds,
            "slo_completion_seconds": slo_completion_seconds,
            "slo_breached": slo_breached,
        },
        "observation_complete": observation_complete,
        "read_only_projection": True,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
        "audit_authority_granted": False,
        "scale_authority_granted": False,
        "classification": classification,
        "reason_code": reason_code,
        "observed_at": observed_at or now_utc(),
    }
    return attach_digest(decision)
