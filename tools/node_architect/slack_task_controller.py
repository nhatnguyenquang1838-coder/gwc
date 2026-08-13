#!/usr/bin/env python3
"""Deterministic TaskController contract and RootCard compiler for Slack Controller–Executor runs."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence
from urllib.parse import unquote, urlparse

AFTER_VALUES = {"CONTINUE", "WAIT_CONTROLLER", "TERMINAL"}
INTERCEPT_FLAGS = ("scope_drift", "authority_drift", "plan_drift", "evidence_conflict", "material_plan_invalidated")
FORBIDDEN_SELECTED_OPTION_KEYS = {"rejected_options", "alternatives", "brainstorm", "brainstorming", "all_options"}

ROOT_CARD_SCHEMA_REF = "schemas/task-controller-root-card.schema.json"
ROOT_CARD_SCHEMA_VERSION = "1.1"
ROOT_CARD_GATES = {"G0", "G1", "G2", "G3", "G4", "G5", "G6"}
ROOT_CARD_COSTS = {"FREE", "metered", "unknown"}
ROOT_CARD_CONTROL_ACTIONS = {"pause", "stop", "approve", "merge"}
CHATGPT_CONVERSATION_SOURCE = "gpt_runtime_current_chat"


def canonical_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _valid_sha(value: str) -> bool:
    return len(value) == 40 and all(c in "0123456789abcdef" for c in value)


def _required_text(value: Any, reason_code: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(reason_code)
    return text


def validate_chatgpt_conversation_deeplink(*, deeplink: str) -> str:
    """Validate an opaque runtime-supplied URL for the current ChatGPT chat.

    The route shape is intentionally not reconstructed or pinned to `/c/...`.
    The Controller runtime is responsible for supplying the actual current-chat URL.
    """
    url = _required_text(deeplink, "TASK_CONTROLLER_CHATGPT_CONVERSATION_REQUIRED")
    parsed = urlparse(url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("TASK_CONTROLLER_CHATGPT_DEEPLINK_INVALID") from exc

    if (
        parsed.scheme != "https"
        or parsed.hostname != "chatgpt.com"
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
    ):
        raise ValueError("TASK_CONTROLLER_CHATGPT_DEEPLINK_INVALID")

    path = unquote(parsed.path or "")
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        raise ValueError("TASK_CONTROLLER_CHATGPT_DEEPLINK_HOME_FORBIDDEN")
    if any(segment.lower() == "share" for segment in segments):
        raise ValueError("TASK_CONTROLLER_CHATGPT_DEEPLINK_SHARE_FORBIDDEN")

    return url


def compile_root_card(
    *,
    run_id: str,
    task_id: str,
    human_owner: str,
    gate: str,
    controller_id: str,
    executor_id: str,
    active_subtask: str,
    progress: str,
    repository: str,
    branch: str,
    head_sha: str,
    ci: str,
    risk: str,
    now: str,
    next_action: str,
    last_material_update: str,
    conversation: Mapping[str, Any],
    executor_model: str = "N/A",
    token_usage: str = "N/A",
    cost: str = "unknown",
    pr: str | None = None,
    actions: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile a canonical RootCard payload; renderers must project this payload without semantic repair."""
    required_values = {
        "run_id": run_id,
        "task_id": task_id,
        "human_owner": human_owner,
        "controller_id": controller_id,
        "executor_id": executor_id,
        "active_subtask": active_subtask,
        "progress": progress,
        "repository": repository,
        "branch": branch,
        "ci": ci,
        "risk": risk,
        "now": now,
        "next": next_action,
        "last_material_update": last_material_update,
        "executor_model": executor_model,
        "token_usage": token_usage,
    }
    normalized = {
        key: _required_text(value, f"TASK_CONTROLLER_ROOT_CARD_{key.upper()}_REQUIRED")
        for key, value in required_values.items()
    }
    if "/" not in normalized["repository"] or normalized["repository"].count("/") != 1:
        raise ValueError("TASK_CONTROLLER_ROOT_CARD_REPOSITORY_INVALID")
    if not _valid_sha(head_sha):
        raise ValueError("TASK_CONTROLLER_ROOT_CARD_HEAD_INVALID")

    normalized_gate = str(gate).upper()
    if normalized_gate not in ROOT_CARD_GATES:
        raise ValueError("TASK_CONTROLLER_ROOT_CARD_GATE_INVALID")
    if cost not in ROOT_CARD_COSTS:
        raise ValueError("TASK_CONTROLLER_ROOT_CARD_COST_INVALID")

    if str(conversation.get("platform", "")).lower() != "chatgpt":
        raise ValueError("TASK_CONTROLLER_ROOT_CARD_CONVERSATION_PLATFORM_INVALID")
    if conversation.get("source") != CHATGPT_CONVERSATION_SOURCE:
        raise ValueError("TASK_CONTROLLER_CHATGPT_CONVERSATION_SOURCE_INVALID")

    deeplink = validate_chatgpt_conversation_deeplink(
        deeplink=str(conversation.get("deeplink", "")),
    )
    normalized_conversation: dict[str, Any] = {
        "platform": "chatgpt",
        "source": CHATGPT_CONVERSATION_SOURCE,
        "deeplink": deeplink,
    }
    if conversation.get("context_key") is not None:
        normalized_conversation["context_key"] = _required_text(
            conversation["context_key"], "TASK_CONTROLLER_ROOT_CARD_CONTEXT_KEY_INVALID"
        )

    requested_actions = dict(actions or {})
    unknown_actions = set(requested_actions) - ROOT_CARD_CONTROL_ACTIONS
    if "open_in_gpt" in requested_actions:
        raise ValueError("TASK_CONTROLLER_ROOT_CARD_OPEN_IN_GPT_DERIVED")
    if unknown_actions:
        raise ValueError("TASK_CONTROLLER_ROOT_CARD_ACTION_INVALID")
    normalized_actions = {
        action: bool(requested_actions.get(action, False))
        for action in ("pause", "stop", "approve", "merge")
    }
    normalized_actions["open_in_gpt"] = {"label": "Open in GPT", "url": deeplink}

    card = {
        "artifact_type": "task-controller-root-card",
        "schema_version": ROOT_CARD_SCHEMA_VERSION,
        "schema_ref": ROOT_CARD_SCHEMA_REF,
        "run_id": normalized["run_id"],
        "task_id": normalized["task_id"],
        "human_owner": normalized["human_owner"],
        "gate": normalized_gate,
        "controller_id": normalized["controller_id"],
        "executor_id": normalized["executor_id"],
        "executor_model": normalized["executor_model"],
        "token_usage": normalized["token_usage"],
        "cost": cost,
        "active_subtask": normalized["active_subtask"],
        "progress": normalized["progress"],
        "repository": normalized["repository"],
        "branch": normalized["branch"],
        "pr": pr,
        "head_sha": head_sha,
        "ci": normalized["ci"],
        "risk": normalized["risk"],
        "now": normalized["now"],
        "next": normalized["next"],
        "last_material_update": normalized["last_material_update"],
        "conversation": normalized_conversation,
        "actions": normalized_actions,
    }
    return {**card, "card_digest": canonical_digest(card)}


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


__all__ = [
    "compile_executor_contract",
    "compile_root_card",
    "controller_next_action",
    "validate_chatgpt_conversation_deeplink",
]
