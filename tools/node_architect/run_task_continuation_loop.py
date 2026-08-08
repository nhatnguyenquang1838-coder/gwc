"""Replay-safe serial continuation decisions for one autonomous pre-prod run."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
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
    cp.setdefault("artifact_type", "autonomous-continuation-checkpoint")
    cp.setdefault("run_id", run_id)
    cp.setdefault("revision", 0)
    cp.setdefault("active_task", None)
    cp.setdefault("active_dispatch_id", None)
    cp.setdefault("active_task_merge_sha", None)
    cp.setdefault("completed_tasks", [])
    cp.setdefault("last_selection_digest", None)
    cp.setdefault("jira_projection_state", None)
    cp.setdefault("last_exact_g5", None)
    cp.setdefault("stop_reason", None)
    return cp


def _store_config(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    config = payload.get("checkpoint_store")
    if config is None:
        return None
    if not isinstance(config, Mapping):
        raise ValueError("checkpoint_store must be an object")
    required = ("path", "controller_task_id", "repository", "branch", "base_sha", "head_sha", "scope_hash")
    missing = [field for field in required if not str(config.get(field, "")).strip()]
    if missing:
        raise ValueError(f"checkpoint_store missing fields: {','.join(missing)}")
    return config


def _checkpoint_api():
    from tools.node_architect import checkpoint_store
    return checkpoint_store


def _load_durable_checkpoint(payload: Mapping[str, Any], run_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    config = _store_config(payload)
    if config is None:
        return _checkpoint(payload.get("checkpoint"), run_id), {
            "checkpoint_persisted": False,
            "checkpoint_store_revision": None,
            "checkpoint_store_digest": None,
        }
    api = _checkpoint_api()
    path = Path(str(config["path"]))
    store = api.load_store(path)
    node_id = str(config.get("node_id") or "autonomous-task-continuation")
    record = api.replay_checkpoint(store, str(config["controller_task_id"]), run_id, node_id)
    state = record.get("state") if isinstance(record, Mapping) else payload.get("checkpoint")
    cp = _checkpoint(state, run_id)
    return cp, {
        "checkpoint_persisted": isinstance(record, Mapping),
        "checkpoint_store_revision": int(store.get("revision", 0)),
        "checkpoint_store_digest": store.get("store_digest"),
    }


def _persist_durable_checkpoint(payload: Mapping[str, Any], cp: Mapping[str, Any]) -> dict[str, Any]:
    config = _store_config(payload)
    if config is None:
        return {
            "checkpoint_persisted": False,
            "checkpoint_store_revision": None,
            "checkpoint_store_digest": None,
        }
    api = _checkpoint_api()
    path = Path(str(config["path"]))
    store = api.load_store(path)
    node_id = str(config.get("node_id") or "autonomous-task-continuation")
    controller_task_id = str(config["controller_task_id"])
    existing = api.replay_checkpoint(store, controller_task_id, str(cp["run_id"]), node_id)
    if isinstance(existing, Mapping) and existing.get("state") == dict(cp):
        return {
            "checkpoint_persisted": True,
            "checkpoint_store_revision": int(store.get("revision", 0)),
            "checkpoint_store_digest": store.get("store_digest"),
        }
    item = api.CheckpointInput(
        task_id=controller_task_id,
        run_id=str(cp["run_id"]),
        node_id=node_id,
        repository=str(config["repository"]),
        branch=str(config["branch"]),
        base_sha=str(config["base_sha"]),
        head_sha=str(config["head_sha"]),
        scope_hash=str(config["scope_hash"]),
        state=dict(cp),
        expected_revision=int(store.get("revision", 0)),
        graph_revision=str(config.get("graph_revision")) if config.get("graph_revision") else None,
    )
    updated = api.persist_to_file(path, item)
    readback = api.load_store(path)
    record = api.replay_checkpoint(readback, controller_task_id, str(cp["run_id"]), node_id)
    if not isinstance(record, Mapping) or record.get("state") != dict(cp):
        raise RuntimeError("CHECKPOINT_READBACK_MISMATCH")
    return {
        "checkpoint_persisted": True,
        "checkpoint_store_revision": int(updated.get("revision", 0)),
        "checkpoint_store_digest": updated.get("store_digest"),
    }


def _exact_g5_pass(active_task: str, expected_merge_sha: str | None, evidence: Any) -> bool:
    return bool(
        expected_merge_sha
        and isinstance(evidence, Mapping)
        and evidence.get("task_id") == active_task
        and evidence.get("merge_sha") == expected_merge_sha
        and evidence.get("status") == "PASS"
        and evidence.get("exact_sha_verified") is True
    )


def _result(payload: Mapping[str, Any], *, cp: dict[str, Any], persistence: Mapping[str, Any],
            outcome: str, reason_code: str, selected_task: str | None,
            claim_requested: bool, selection: Mapping[str, Any] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": "1.0",
        "artifact_type": "autonomous-task-continuation-decision",
        "run_id": str(payload["run_id"]),
        "dispatch_id": str(payload["dispatch_id"]),
        "outcome": outcome,
        "reason_code": reason_code,
        "selected_task": selected_task,
        "claim_requested": claim_requested,
        "parallel_execution_allowed": False,
        "authority_granted": False,
        "checkpoint": cp,
        **dict(persistence),
    }
    if selection is not None:
        result["selection"] = dict(selection)
    result["decision_digest"] = _digest(result)
    return result


def run_task_continuation_loop(payload: Mapping[str, Any]) -> dict[str, Any]:
    run_id = str(payload.get("run_id", "")).strip()
    dispatch_id = str(payload.get("dispatch_id", "")).strip()
    if not run_id or not dispatch_id:
        raise ValueError("run_id and dispatch_id are required")
    cp, loaded_persistence = _load_durable_checkpoint(payload, run_id)
    if cp["run_id"] != run_id:
        raise ValueError("checkpoint run_id mismatch")

    stop = payload.get("stop_conditions", {})
    if not isinstance(stop, Mapping):
        raise ValueError("stop_conditions must be an object")
    for field, code in STOP_CONDITIONS:
        if stop.get(field) is True:
            cp = {**cp, "revision": int(cp.get("revision", 0)) + 1, "stop_reason": code}
            persistence = _persist_durable_checkpoint(payload, cp)
            return _result(payload, cp=cp, persistence=persistence, outcome="STOPPED",
                           reason_code=code, selected_task=None, claim_requested=False)

    active = cp.get("active_task")
    merge_readback = payload.get("active_task_merge_sha_readback")
    if active and merge_readback is not None:
        merge_sha = str(merge_readback)
        if len(merge_sha) != 40 or any(ch not in "0123456789abcdef" for ch in merge_sha):
            raise ValueError("active_task_merge_sha_readback must be a lowercase 40-hex SHA")
        if cp.get("active_task_merge_sha") not in {None, merge_sha}:
            raise ValueError("active task merge SHA drift")
        if cp.get("active_task_merge_sha") != merge_sha:
            cp = {**cp, "revision": int(cp.get("revision", 0)) + 1, "active_task_merge_sha": merge_sha}
            loaded_persistence = _persist_durable_checkpoint(payload, cp)

    projection_state = payload.get("jira_projection_state")
    if projection_state is not None:
        if not isinstance(projection_state, Mapping):
            raise ValueError("jira_projection_state must be an object")
        if cp.get("jira_projection_state") != dict(projection_state):
            cp = {**cp, "revision": int(cp.get("revision", 0)) + 1, "jira_projection_state": dict(projection_state)}
            loaded_persistence = _persist_durable_checkpoint(payload, cp)

    if active:
        g5 = payload.get("previous_task_g5")
        if cp.get("active_dispatch_id") == dispatch_id and not _exact_g5_pass(active, cp.get("active_task_merge_sha"), g5):
            persistence = _persist_durable_checkpoint(payload, cp)
            return _result(payload, cp=cp, persistence=persistence, outcome="FENCED",
                           reason_code="DUPLICATE_DISPATCH_FENCED", selected_task=str(active), claim_requested=False)
        if not _exact_g5_pass(active, cp.get("active_task_merge_sha"), g5):
            persistence = _persist_durable_checkpoint(payload, cp)
            return _result(payload, cp=cp, persistence=persistence, outcome="WAITING",
                           reason_code="WAITING_FOR_EXACT_G5", selected_task=str(active), claim_requested=False)
        completed = list(dict.fromkeys([*cp.get("completed_tasks", []), active]))
        cp = {
            **cp,
            "revision": int(cp.get("revision", 0)) + 1,
            "active_task": None,
            "active_dispatch_id": None,
            "active_task_merge_sha": None,
            "completed_tasks": completed,
            "last_exact_g5": dict(g5) if isinstance(g5, Mapping) else None,
            "stop_reason": None,
        }

    selection_input = payload.get("selection_input")
    if not isinstance(selection_input, Mapping):
        raise ValueError("selection_input is required when no task is active")
    if str(selection_input.get("run_id", "")) != run_id:
        raise ValueError("selection_input run_id mismatch")
    selection = select_autonomous_jira_task(selection_input)
    selected = selection.get("selected_task")
    if not selected:
        cp = {**cp, "last_selection_digest": selection["selection_digest"]}
        persistence = _persist_durable_checkpoint(payload, cp)
        return _result(payload, cp=cp, persistence=persistence, outcome="IDLE",
                       reason_code="NO_ELIGIBLE_TASK", selected_task=None, claim_requested=False, selection=selection)

    if selected in cp.get("completed_tasks", []):
        raise ValueError("selector returned a completed task")
    cp = {
        **cp,
        "revision": int(cp.get("revision", 0)) + 1,
        "active_task": selected,
        "active_dispatch_id": dispatch_id,
        "active_task_merge_sha": None,
        "last_selection_digest": selection["selection_digest"],
        "stop_reason": None,
    }
    persistence = _persist_durable_checkpoint(payload, cp)
    return _result(payload, cp=cp, persistence=persistence, outcome="CLAIM_ONE_TASK",
                   reason_code="SERIAL_TASK_SELECTED", selected_task=str(selected), claim_requested=True,
                   selection=selection)
