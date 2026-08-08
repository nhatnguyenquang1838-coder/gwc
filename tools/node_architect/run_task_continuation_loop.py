"""Replay-safe serial continuation decisions for one autonomous pre-prod run."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

try:
    from .select_autonomous_jira_task import select_autonomous_jira_task
except ImportError:  # pragma: no cover - direct script/import fallback
    from select_autonomous_jira_task import select_autonomous_jira_task

STOP_CONDITIONS = (
    ("policy_expired", "POLICY_EXPIRED"),
    ("graph_drift", "GRAPH_DRIFT"),
    ("task_scope_drift", "TASK_SCOPE_DRIFT"),
    ("terminal_blocker", "TERMINAL_BLOCKER"),
    ("repair_budget_exhausted", "REPAIR_BUDGET_EXHAUSTED"),
    ("human_authority_required", "HUMAN_AUTHORITY_REQUIRED"),
)


def _digest(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _checkpoint(value: Any, run_id: str) -> dict[str, Any]:
    cp = dict(value) if isinstance(value, Mapping) else {}
    cp.setdefault("schema_version", "1.0")
    cp.setdefault("run_id", run_id)
    cp.setdefault("revision", 0)
    cp.setdefault("active_task", None)
    cp.setdefault("active_dispatch_id", None)
    cp.setdefault("active_task_merge_sha", None)
    cp.setdefault("completed_tasks", [])
    cp.setdefault("last_selection_digest", None)
    return cp


def _exact_g5_pass(active_task: str, expected_merge_sha: str | None, evidence: Any) -> bool:
    return bool(
        expected_merge_sha
        and isinstance(evidence, Mapping)
        and evidence.get("task_id") == active_task
        and evidence.get("merge_sha") == expected_merge_sha
        and evidence.get("status") == "PASS"
        and evidence.get("exact_sha_verified") is True
    )


def run_task_continuation_loop(payload: Mapping[str, Any]) -> dict[str, Any]:
    run_id = str(payload.get("run_id", "")).strip()
    dispatch_id = str(payload.get("dispatch_id", "")).strip()
    if not run_id or not dispatch_id:
        raise ValueError("run_id and dispatch_id are required")
    cp = _checkpoint(payload.get("checkpoint"), run_id)
    if cp["run_id"] != run_id:
        raise ValueError("checkpoint run_id mismatch")

    stop = payload.get("stop_conditions", {})
    if not isinstance(stop, Mapping):
        raise ValueError("stop_conditions must be an object")
    for field, code in STOP_CONDITIONS:
        if stop.get(field) is True:
            result = {
                "schema_version": "1.0",
                "artifact_type": "autonomous-task-continuation-decision",
                "run_id": run_id,
                "dispatch_id": dispatch_id,
                "outcome": "STOPPED",
                "reason_code": code,
                "selected_task": None,
                "claim_requested": False,
                "parallel_execution_allowed": False,
                "authority_granted": False,
                "checkpoint": cp,
            }
            result["decision_digest"] = _digest(result)
            return result

    active = cp.get("active_task")
    if active:
        if cp.get("active_dispatch_id") == dispatch_id and not _exact_g5_pass(active, cp.get("active_task_merge_sha"), payload.get("previous_task_g5")):
            outcome, reason = "FENCED", "DUPLICATE_DISPATCH_FENCED"
        elif not _exact_g5_pass(active, cp.get("active_task_merge_sha"), payload.get("previous_task_g5")):
            outcome, reason = "WAITING", "WAITING_FOR_EXACT_G5"
        else:
            completed = list(dict.fromkeys([*cp.get("completed_tasks", []), active]))
            cp = {
                **cp,
                "revision": int(cp.get("revision", 0)) + 1,
                "active_task": None,
                "active_dispatch_id": None,
                "active_task_merge_sha": None,
                "completed_tasks": completed,
            }
            active = None
            outcome = reason = ""
        if active:
            result = {
                "schema_version": "1.0",
                "artifact_type": "autonomous-task-continuation-decision",
                "run_id": run_id,
                "dispatch_id": dispatch_id,
                "outcome": outcome,
                "reason_code": reason,
                "selected_task": active,
                "claim_requested": False,
                "parallel_execution_allowed": False,
                "authority_granted": False,
                "checkpoint": cp,
            }
            result["decision_digest"] = _digest(result)
            return result

    selection_input = payload.get("selection_input")
    if not isinstance(selection_input, Mapping):
        raise ValueError("selection_input is required when no task is active")
    if str(selection_input.get("run_id", "")) != run_id:
        raise ValueError("selection_input run_id mismatch")
    selection = select_autonomous_jira_task(selection_input)
    selected = selection.get("selected_task")
    if not selected:
        result = {
            "schema_version": "1.0",
            "artifact_type": "autonomous-task-continuation-decision",
            "run_id": run_id,
            "dispatch_id": dispatch_id,
            "outcome": "IDLE",
            "reason_code": "NO_ELIGIBLE_TASK",
            "selected_task": None,
            "claim_requested": False,
            "parallel_execution_allowed": False,
            "authority_granted": False,
            "selection": selection,
            "checkpoint": cp,
        }
        result["decision_digest"] = _digest(result)
        return result

    if selected in cp.get("completed_tasks", []):
        raise ValueError("selector returned a completed task")
    new_cp = {
        **cp,
        "revision": int(cp.get("revision", 0)) + 1,
        "active_task": selected,
        "active_dispatch_id": dispatch_id,
        "last_selection_digest": selection["selection_digest"],
    }
    result = {
        "schema_version": "1.0",
        "artifact_type": "autonomous-task-continuation-decision",
        "run_id": run_id,
        "dispatch_id": dispatch_id,
        "outcome": "CLAIM_ONE_TASK",
        "reason_code": "SERIAL_TASK_SELECTED",
        "selected_task": selected,
        "claim_requested": True,
        "parallel_execution_allowed": False,
        "authority_granted": False,
        "selection": selection,
        "checkpoint": new_cp,
    }
    result["decision_digest"] = _digest(result)
    return result
