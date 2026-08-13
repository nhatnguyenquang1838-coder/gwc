#!/usr/bin/env python3
"""Deterministic TaskController contract compiler for the Slack Controller–Executor MVP."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

AFTER_VALUES = {"CONTINUE", "WAIT_CONTROLLER", "TERMINAL"}
INTERCEPT_FLAGS = ("scope_drift", "authority_drift", "plan_drift", "evidence_conflict", "material_plan_invalidated")
FORBIDDEN_SELECTED_OPTION_KEYS = {"rejected_options", "alternatives", "brainstorm", "brainstorming", "all_options"}


def canonical_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _valid_sha(value: str) -> bool:
    return len(value) == 40 and all(c in "0123456789abcdef" for c in value)


def compile_executor_contract(*, task_id: str, repository: str, base_sha: str, branch: str,
                              selected_option: Mapping[str, Any], g2_authority_ref: str,
                              subtasks: Sequence[Mapping[str, Any]], controller_id: str,
                              executor_id: str, slack_thread_ref: str | None = None) -> dict[str, Any]:
    """Compile only the selected G1 option plus exact G2 boundary into a 3–5 subtask contract."""
    if not task_id or "/" not in repository or not _valid_sha(base_sha) or not branch:
        raise ValueError("TASK_CONTROLLER_BINDING_INVALID")
    if not controller_id or not executor_id or controller_id == executor_id:
        raise ValueError("TASK_CONTROLLER_ROLE_IDENTITY_INVALID")
    if not g2_authority_ref:
        raise ValueError("TASK_CONTROLLER_G2_AUTHORITY_REQUIRED")
    if any(key in selected_option for key in FORBIDDEN_SELECTED_OPTION_KEYS):
        raise ValueError("TASK_CONTROLLER_SELECTED_OPTION_CONTAINS_NOISE")
    if len(subtasks) < 3 or len(subtasks) > 5:
        raise ValueError("TASK_CONTROLLER_SUBTASK_COUNT_INVALID")
    required = ("id", "objective", "allowed_work", "expected_output", "report_requirement", "after_report")
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in subtasks:
        missing = [field for field in required if not item.get(field)]
        if missing:
            raise ValueError("TASK_CONTROLLER_SUBTASK_FIELDS_MISSING:" + ",".join(missing))
        subtask_id = str(item["id"])
        if subtask_id in seen_ids:
            raise ValueError("TASK_CONTROLLER_SUBTASK_ID_DUPLICATE")
        seen_ids.add(subtask_id)
        after = str(item["after_report"]).upper()
        if after not in AFTER_VALUES:
            raise ValueError("TASK_CONTROLLER_AFTER_REPORT_INVALID")
        normalized.append({
            "id": subtask_id,
            "objective": str(item["objective"]),
            "allowed_work": item["allowed_work"],
            "expected_output": item["expected_output"],
            "report_requirement": item["report_requirement"],
            "after_report": after,
        })
    contract = {
        "artifact_type": "slack-task-controller-executor-contract",
        "schema_version": "1.1",
        "task_id": task_id,
        "repository": repository,
        "base_sha": base_sha,
        "branch": branch,
        "controller_id": controller_id,
        "executor_id": executor_id,
        "slack_thread_ref": slack_thread_ref,
        "selected_option": dict(selected_option),
        "g2_authority_ref": g2_authority_ref,
        "subtasks": normalized,
        "communication_surface": "SLACK",
        "slack_is_authority": False,
        "protocol_ref": "agents/shared/slack-controller-executor-protocol.md",
    }
    return {**contract, "contract_digest": canonical_digest(contract)}


def controller_next_action(report: Mapping[str, Any], *, expected_subtask_id: str) -> dict[str, Any]:
    """Classify one semantic Executor milestone report; tool chatter is outside this contract."""
    if any(report.get(flag) is True for flag in INTERCEPT_FLAGS):
        return {"outcome": "INTERCEPT", "action": "WAIT", "reason_code": "TASK_CONTROLLER_MATERIAL_DRIFT"}
    if str(report.get("subtask_id", "")) != expected_subtask_id:
        return {"outcome": "INTERCEPT", "action": "REPLAN", "reason_code": "TASK_CONTROLLER_PLAN_DRIFT"}
    status = str(report.get("status", "")).upper()
    if status in {"BLOCKED", "FAILED"}:
        return {"outcome": "TERMINAL", "action": "SAFE_STOP", "reason_code": "TASK_CONTROLLER_EXECUTOR_BLOCKED"}
    after = str(report.get("after_report", "")).upper()
    if after == "WAIT_CONTROLLER":
        return {"outcome": "WAIT_CONTROLLER", "action": "REVIEW_EVIDENCE", "reason_code": "TASK_CONTROLLER_REVIEW_REQUIRED"}
    if after == "TERMINAL":
        return {"outcome": "TERMINAL", "action": "VERIFY_TERMINAL_EVIDENCE", "reason_code": "TASK_CONTROLLER_EXECUTOR_TERMINAL"}
    if after == "CONTINUE" and status in {"RUNNING", "DONE"}:
        return {"outcome": "CONTINUE", "action": "MONITOR", "reason_code": "TASK_CONTROLLER_CONTRACT_ON_TRACK"}
    return {"outcome": "INTERCEPT", "action": "WAIT", "reason_code": "TASK_CONTROLLER_REPORT_INVALID"}


__all__ = ["compile_executor_contract", "controller_next_action"]
