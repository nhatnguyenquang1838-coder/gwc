"""Deterministic, side-effect-free Jira task selection for an autonomous run."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

READY_STATUSES = {"to do", "todo", "ready", "open", "backlog"}
UNSAFE_DONE_STATES = {
    "cancelled": "SEMANTICALLY_CANCELLED",
    "canceled": "SEMANTICALLY_CANCELLED",
    "refinement-only": "REFINEMENT_ONLY",
    "refinement_only": "REFINEMENT_ONLY",
    "superseded": "SUPERSEDED",
    "no-deliverable": "NO_DELIVERABLE",
    "no_deliverable": "NO_DELIVERABLE",
}
PRIORITY_RANK = {
    "highest": 0,
    "critical": 0,
    "high": 1,
    "medium": 2,
    "normal": 2,
    "low": 3,
    "lowest": 4,
}


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(payload: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _priority_rank(value: Any) -> tuple[int, str]:
    if isinstance(value, bool):
        return (100, str(value))
    if isinstance(value, int):
        return (value, str(value))
    text = str(value or "").strip().lower()
    if text.isdigit():
        return (int(text), text)
    return (PRIORITY_RANK.get(text, 100), text)


def _manifest_ids(manifest: Mapping[str, Any]) -> list[str]:
    items = manifest.get("allowed_tasks", [])
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
        raise ValueError("manifest.allowed_tasks must be a list")
    task_ids: list[str] = []
    for item in items:
        if isinstance(item, str):
            task_id = item
        elif isinstance(item, Mapping):
            task_id = str(item.get("task_id", ""))
        else:
            task_id = ""
        if not task_id:
            raise ValueError("each manifest task must have task_id")
        if task_id in task_ids:
            raise ValueError(f"duplicate manifest task: {task_id}")
        task_ids.append(task_id)
    return task_ids


def _dependency_safety(task_id: str, evidence: Mapping[str, Any] | None) -> tuple[bool, list[str], bool, list[str]]:
    """Return safe, reasons, unsafe_done, evidence_refs."""
    if not isinstance(evidence, Mapping):
        return False, ["DEPENDENCY_EVIDENCE_MISSING"], False, []
    status = str(evidence.get("jira_status", "")).strip()
    refs = [str(x) for x in evidence.get("evidence_refs", []) if str(x)]
    if status.casefold() != "done":
        return False, ["DEPENDENCY_NOT_DONE"], False, refs

    reasons: list[str] = []
    semantic = str(evidence.get("semantic_state", "deliverable")).strip().lower()
    if semantic in UNSAFE_DONE_STATES:
        reasons.append(UNSAFE_DONE_STATES[semantic])
    if evidence.get("repository_implementation") is not True:
        reasons.append("REPOSITORY_IMPLEMENTATION_MISSING")
    if evidence.get("exact_sha_verified") is not True:
        reasons.append("EXACT_SHA_EVIDENCE_MISSING")
    if not refs:
        reasons.append("EVIDENCE_REF_MISSING")
    return not reasons, reasons, bool(reasons), refs


def select_autonomous_jira_task(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Select exactly one eligible task without mutating Jira or granting authority."""
    run_id = str(payload.get("run_id", "")).strip()
    active_lane = str(payload.get("active_lane", "")).strip()
    if not run_id or not active_lane:
        raise ValueError("run_id and active_lane are required")

    excluded_lanes = sorted({str(x) for x in payload.get("excluded_lanes", []) if str(x)})
    manifest = payload.get("manifest")
    if not isinstance(manifest, Mapping):
        raise ValueError("manifest must be an object")
    manifest_ids = _manifest_ids(manifest)
    manifest_order = {task_id: index for index, task_id in enumerate(manifest_ids)}

    raw_tasks = payload.get("jira_tasks", [])
    if not isinstance(raw_tasks, Sequence) or isinstance(raw_tasks, (str, bytes)):
        raise ValueError("jira_tasks must be a list")
    jira_by_id: dict[str, Mapping[str, Any]] = {}
    for item in raw_tasks:
        if not isinstance(item, Mapping) or not item.get("task_id"):
            raise ValueError("every jira task must be an object with task_id")
        task_id = str(item["task_id"])
        if task_id in jira_by_id:
            raise ValueError(f"duplicate Jira task snapshot: {task_id}")
        jira_by_id[task_id] = item

    dep_map = payload.get("dependency_evidence", {})
    if not isinstance(dep_map, Mapping):
        raise ValueError("dependency_evidence must be an object keyed by task id")

    dependency_rows: list[dict[str, Any]] = []
    unsafe_done: dict[str, dict[str, Any]] = {}
    eligible: list[tuple[tuple[int, str], int, str]] = []

    for task_id in manifest_ids:
        task = jira_by_id.get(task_id)
        if task is None:
            continue
        lane = str(task.get("lane", ""))
        if lane != active_lane or lane in excluded_lanes:
            continue
        if str(task.get("status", "")).strip().casefold() not in READY_STATUSES:
            continue

        dependencies = task.get("dependencies", [])
        if not isinstance(dependencies, Sequence) or isinstance(dependencies, (str, bytes)):
            raise ValueError(f"dependencies for {task_id} must be a list")
        all_safe = True
        for dep in dependencies:
            dep_id = str(dep)
            evidence = dep_map.get(dep_id)
            safe, reasons, is_unsafe_done, refs = _dependency_safety(dep_id, evidence if isinstance(evidence, Mapping) else None)
            dependency_rows.append({
                "candidate_task": task_id,
                "dependency_task": dep_id,
                "jira_status": str(evidence.get("jira_status", "UNKNOWN")) if isinstance(evidence, Mapping) else "UNKNOWN",
                "safe": safe,
                "reasons": reasons,
                "evidence_refs": refs,
            })
            if is_unsafe_done:
                row = unsafe_done.setdefault(dep_id, {"task_id": dep_id, "reasons": [], "evidence_refs": refs})
                row["reasons"] = sorted(set(row["reasons"]) | set(reasons))
                row["evidence_refs"] = sorted(set(row["evidence_refs"]) | set(refs))
            all_safe = all_safe and safe
        if all_safe:
            eligible.append((_priority_rank(task.get("priority")), manifest_order[task_id], task_id))

    eligible.sort(key=lambda row: (row[0][0], row[0][1], row[1], row[2]))
    eligible_ids = [row[2] for row in eligible]
    selected = eligible_ids[0] if eligible_ids else None
    reason = (
        "SELECTED_DEPENDENCY_READY_PRIORITY_MANIFEST_ORDER"
        if selected
        else "NO_ELIGIBLE_TASK_IN_ACTIVE_LANE"
    )
    result: dict[str, Any] = {
        "schema_version": "1.0",
        "artifact_type": "autonomous-task-selection",
        "run_id": run_id,
        "active_lane": active_lane,
        "excluded_lanes": excluded_lanes,
        "selected_task": selected,
        "selection_reason": reason,
        "dependency_evidence": dependency_rows,
        "unsafe_done_dependencies": [unsafe_done[k] for k in sorted(unsafe_done)],
        "next_eligible_tasks": eligible_ids[1:] if selected else [],
        "candidate_count": len(manifest_ids),
        "eligible_count": len(eligible_ids),
        "parallel_execution_allowed": False,
        "authority_granted": False,
    }
    result["selection_digest"] = _digest(result)
    return result
