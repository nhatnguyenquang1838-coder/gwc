"""Honest, projection-only Jira state reconciliation for autonomous task runs."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any


def _digest(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _legal(current: str, intended: str, transitions: Any) -> bool:
    if current == intended:
        return True
    if not isinstance(transitions, Sequence) or isinstance(transitions, (str, bytes)):
        return False
    for item in transitions:
        if isinstance(item, Mapping) and str(item.get("from")) == current and str(item.get("to")) == intended:
            return True
    return False


def reconcile_autonomous_task_state(observation: Mapping[str, Any]) -> dict[str, Any]:
    task_id = str(observation.get("task_id", "")).strip()
    current = str(observation.get("current_status", "")).strip()
    intended = str(observation.get("intended_status", "")).strip()
    canonical = str(observation.get("canonical_execution_status", "")).strip()
    write_result = str(observation.get("write_result", "not_attempted")).strip().lower()
    readback = observation.get("readback_status")
    dispatch_id = str(observation.get("dispatch_id", "")).strip()
    if not all((task_id, current, intended, canonical, dispatch_id)):
        raise ValueError("task_id/current_status/intended_status/canonical_execution_status/dispatch_id are required")
    if write_result not in {"not_attempted", "success", "failed", "unknown"}:
        raise ValueError("invalid write_result")

    legal = _legal(current, intended, observation.get("legal_transitions", []))
    projection_status = "LATE_RECONCILIATION_REQUIRED"
    reason_code = "JIRA_PROJECTION_NOT_ATTEMPTED"
    synchronized = False

    if current == intended:
        projection_status = "SYNCHRONIZED"
        reason_code = "JIRA_ALREADY_SYNCHRONIZED"
        synchronized = True
    elif not legal:
        projection_status = "BLOCKED"
        reason_code = "JIRA_TRANSITION_ILLEGAL"
    elif write_result == "failed":
        reason_code = "JIRA_WRITE_FAILED"
    elif write_result == "unknown":
        reason_code = "JIRA_WRITE_OUTCOME_UNKNOWN"
    elif write_result == "success" and str(readback or "") == intended:
        projection_status = "SYNCHRONIZED"
        reason_code = "JIRA_PROJECTION_SYNCHRONIZED"
        synchronized = True
    elif write_result == "success":
        reason_code = "JIRA_READBACK_MISMATCH"

    checkpoint = {
        "task_id": task_id,
        "dispatch_id": dispatch_id,
        "canonical_execution_status": canonical,
        "jira_status_before": current,
        "jira_status_intended": intended,
        "jira_status_readback": str(readback) if readback is not None else None,
        "projection_status": projection_status,
        "reason_code": reason_code,
    }
    result = {
        **checkpoint,
        "synchronized": synchronized,
        "late_reconciliation_required": projection_status == "LATE_RECONCILIATION_REQUIRED",
        "canonical_execution_truth_preserved": True,
        "authority_granted": False,
        "checkpoint": checkpoint,
    }
    result["reconciliation_digest"] = _digest(result)
    return result
