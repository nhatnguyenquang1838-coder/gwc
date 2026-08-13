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


# --- Thread identity resolution (fail-closed) -------------------------------------------
#
# Deterministic helper enforcing the canonical invariant: exactly one active RootCard/thread
# per logical task lifecycle, keyed by `thread_key=<project_id>:<task_id>`. A *run* is an event
# inside the task thread and MUST reuse the same thread.
THREAD_ACTION_CREATE_ROOT = "CREATE_ROOT"
THREAD_ACTION_REPLY_EXISTING = "REPLY_EXISTING_THREAD"
THREAD_ACTION_REPLACE = "REPLACE_THREAD"


def resolve_thread_action(*, thread_key: str, existing_threads: Sequence[Mapping[str, Any]],
                          requested_task_id: str | None = None, reset_requested: bool = False,
                          original_inaccessible: bool = False, force_create_root: bool = False) -> dict[str, Any]:
    """Resolve the Slack action for a Controller dispatch against the canonical thread invariant.

    Args:
        thread_key: canonical binding key `<project_id>:<task_id>`.
        existing_threads: candidate bindings already recorded for `thread_key`
            (each mapping MUST carry at least `thread_ref`; may carry `task_id`, `superseded`).
        requested_task_id: the task the new dispatch targets (used to detect a genuinely different task).
        reset_requested: explicit `THREAD_RESET` supplied by the Controller.
        original_inaccessible: the previously bound thread can no longer be posted to.
        force_create_root: caller explicitly demands a fresh root. Fail-closed — refused when an active
            same-task binding already exists without reset/inaccessible, raising
            `TASK_CONTROLLER_DUPLICATE_ROOT_FOR_TASK`.

    Returns a dict with `action` (one of THREAD_ACTION_*) and a `reason_code`.
    Fail-closed: ambiguity, invalid key, or an unauthorized duplicate raises ValueError.
    """
    if not thread_key or ":" not in thread_key:
        raise ValueError("TASK_CONTROLLER_THREAD_KEY_INVALID")
    active = [t for t in existing_threads if not t.get("superseded")]

    # 1) multiple live bindings for the same key -> ambiguous, fail closed
    if len(active) > 1:
        raise ValueError("TASK_CONTROLLER_THREAD_BINDING_AMBIGUOUS")

    # 2) no active binding -> safe to create the root
    if not active:
        if force_create_root or reset_requested or original_inaccessible:
            return {"action": THREAD_ACTION_CREATE_ROOT, "reason_code": "TASK_CONTROLLER_NO_PRIOR_BINDING"}
        return {"action": THREAD_ACTION_CREATE_ROOT, "reason_code": "TASK_CONTROLLER_NO_PRIOR_BINDING"}

    existing = active[0]
    existing_task = existing.get("task_id")

    # 3) genuinely different task -> allowed to create/replace a fresh root for the new task
    if requested_task_id and existing_task and requested_task_id != existing_task:
        return {"action": THREAD_ACTION_CREATE_ROOT, "reason_code": "TASK_CONTROLLER_DIFFERENT_TASK"}

    # 4) explicit demand for a new root over an active same-task binding -> duplicate root fault
    if force_create_root:
        raise ValueError("TASK_CONTROLLER_DUPLICATE_ROOT_FOR_TASK")

    # 5) replacement requires explicit reset OR inaccessible original, with supersession metadata
    if reset_requested or original_inaccessible:
        return {"action": THREAD_ACTION_REPLACE, "reason_code": "TASK_CONTROLLER_SUPERSESSION_REQUIRED"}

    # 6) same task, already bound, no reset -> reuse the existing thread
    return {"action": THREAD_ACTION_REPLY_EXISTING, "reason_code": "TASK_CONTROLLER_REUSE_EXISTING_THREAD"}


__all__ = ["compile_executor_contract", "controller_next_action", "resolve_thread_action",
           "THREAD_ACTION_CREATE_ROOT", "THREAD_ACTION_REPLY_EXISTING", "THREAD_ACTION_REPLACE"]
