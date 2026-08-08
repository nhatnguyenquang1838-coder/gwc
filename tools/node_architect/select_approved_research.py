"""Deterministically select one Human-approved research record in the active lane."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

READY_RESEARCH_STATUSES = {"in review", "approved", "ready for execution", "ready_for_execution"}
UNSAFE_DONE_STATES = {
    "cancelled": "SEMANTICALLY_CANCELLED",
    "canceled": "SEMANTICALLY_CANCELLED",
    "refinement-only": "REFINEMENT_ONLY",
    "refinement_only": "REFINEMENT_ONLY",
    "superseded": "SUPERSEDED",
    "no-deliverable": "NO_DELIVERABLE",
    "no_deliverable": "NO_DELIVERABLE",
}
PRIORITY_RANK = {"highest": 0, "critical": 0, "high": 1, "medium": 2, "normal": 2, "low": 3, "lowest": 4}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode()).hexdigest()


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must contain timezone")
    return parsed.astimezone(timezone.utc)


def _priority(value: Any) -> tuple[int, str]:
    text = str(value or "").strip().lower()
    if text.isdigit():
        return int(text), text
    return PRIORITY_RANK.get(text, 100), text


def _dependency_safe(evidence: Any) -> tuple[bool, list[str], bool, list[str]]:
    if not isinstance(evidence, Mapping):
        return False, ["DEPENDENCY_EVIDENCE_MISSING"], False, []
    refs = [str(x) for x in evidence.get("evidence_refs", []) if str(x)]
    if str(evidence.get("jira_status", "")).strip().casefold() != "done":
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


def select_approved_research(payload: Mapping[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    run_id = str(payload.get("run_id", "")).strip()
    active_lane = str(payload.get("active_lane", "")).strip()
    trigger_mode = str(payload.get("trigger_mode", "")).strip()
    if not run_id or not active_lane:
        raise ValueError("run_id and active_lane are required")
    if trigger_mode not in {"immediate_after_approval", "scheduled_poll"}:
        raise ValueError("unsupported trigger_mode")
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    excluded_lanes = sorted({str(x) for x in payload.get("excluded_lanes", []) if str(x)})
    research = payload.get("research_records", [])
    approvals = payload.get("approvals", [])
    dep_map = payload.get("dependency_evidence", {})
    if not isinstance(research, Sequence) or isinstance(research, (str, bytes)):
        raise ValueError("research_records must be a list")
    if not isinstance(approvals, Sequence) or isinstance(approvals, (str, bytes)):
        raise ValueError("approvals must be a list")
    approval_by_ref: dict[str, Mapping[str, Any]] = {}
    for item in approvals:
        if not isinstance(item, Mapping) or not item.get("research_ref"):
            raise ValueError("approval must contain research_ref")
        ref = str(item["research_ref"])
        if ref in approval_by_ref:
            raise ValueError(f"duplicate approval for {ref}")
        approval_by_ref[ref] = item

    eligible: list[tuple[tuple[int, str], int, str, Mapping[str, Any]]] = []
    dependency_rows: list[dict[str, Any]] = []
    unsafe_done: dict[str, dict[str, Any]] = {}
    rejected: list[dict[str, str]] = []
    for order, record in enumerate(research):
        if not isinstance(record, Mapping) or not record.get("research_ref"):
            raise ValueError("research record must contain research_ref")
        ref = str(record["research_ref"])
        lane = str(record.get("lane", ""))
        if lane != active_lane or lane in excluded_lanes:
            rejected.append({"research_ref": ref, "reason_code": "RESEARCH_OUTSIDE_ACTIVE_LANE"})
            continue
        if str(record.get("status", "")).strip().casefold() not in READY_RESEARCH_STATUSES:
            rejected.append({"research_ref": ref, "reason_code": "RESEARCH_STATUS_NOT_EXECUTABLE"})
            continue
        approval = approval_by_ref.get(ref)
        if not isinstance(approval, Mapping):
            rejected.append({"research_ref": ref, "reason_code": "RESEARCH_APPROVAL_MISSING"})
            continue
        if approval.get("research_digest") != record.get("research_digest"):
            rejected.append({"research_ref": ref, "reason_code": "RESEARCH_DIGEST_DRIFT"})
            continue
        if approval.get("repository") != record.get("repository") or approval.get("active_lane") != lane:
            rejected.append({"research_ref": ref, "reason_code": "RESEARCH_SCOPE_DRIFT"})
            continue
        try:
            if _parse_utc(str(approval.get("expires_at", ""))) <= now:
                rejected.append({"research_ref": ref, "reason_code": "RESEARCH_APPROVAL_EXPIRED"})
                continue
        except (TypeError, ValueError):
            rejected.append({"research_ref": ref, "reason_code": "RESEARCH_APPROVAL_INVALID"})
            continue
        all_safe = True
        dependencies = record.get("dependencies", [])
        if not isinstance(dependencies, Sequence) or isinstance(dependencies, (str, bytes)):
            raise ValueError(f"dependencies for {ref} must be a list")
        for dep in dependencies:
            dep_id = str(dep)
            evidence = dep_map.get(dep_id) if isinstance(dep_map, Mapping) else None
            safe, reasons, is_unsafe_done, refs = _dependency_safe(evidence)
            dependency_rows.append({"candidate_research": ref, "dependency_task": dep_id, "safe": safe, "reasons": reasons, "evidence_refs": refs})
            if is_unsafe_done:
                unsafe_done[dep_id] = {"task_id": dep_id, "reasons": reasons, "evidence_refs": refs}
            all_safe = all_safe and safe
        if not all_safe:
            rejected.append({"research_ref": ref, "reason_code": "RESEARCH_DEPENDENCY_UNSAFE"})
            continue
        eligible.append((_priority(record.get("priority")), order, ref, approval))

    eligible.sort(key=lambda row: (row[0][0], row[0][1], row[1], row[2]))
    selected = eligible[0][2] if eligible else None
    approval = eligible[0][3] if eligible else None
    result = {
        "schema_version": "1.0", "artifact_type": "approved-research-selection", "run_id": run_id,
        "trigger_mode": trigger_mode, "active_lane": active_lane, "excluded_lanes": excluded_lanes,
        "selected_research": selected, "selected_approval_id": approval.get("approval_id") if approval else None,
        "selection_reason": "SELECTED_APPROVED_RESEARCH" if selected else "NO_ELIGIBLE_APPROVED_RESEARCH",
        "next_eligible_research": [row[2] for row in eligible[1:]], "dependency_evidence": dependency_rows,
        "unsafe_done_dependencies": [unsafe_done[k] for k in sorted(unsafe_done)], "rejected": rejected,
        "parallel_execution_allowed": False, "authority_granted": False,
    }
    result["selection_digest"] = _digest(result)
    return result
