"""Honest, projection-only Jira state reconciliation for autonomous task runs."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
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


def _checkpoint_api():
    from tools.node_architect import checkpoint_store
    return checkpoint_store


def _persist_reconciliation(observation: Mapping[str, Any], checkpoint: Mapping[str, Any]) -> dict[str, Any]:
    config = observation.get("checkpoint_store")
    if config is None:
        return {"checkpoint_persisted": False, "checkpoint_store_revision": None, "checkpoint_store_digest": None}
    if not isinstance(config, Mapping):
        raise ValueError("checkpoint_store must be an object")
    run_id = str(observation.get("run_id", "")).strip()
    if not run_id:
        raise ValueError("run_id is required when checkpoint_store is configured")
    required = ("path", "repository", "branch", "base_sha", "head_sha", "scope_hash")
    missing = [field for field in required if not str(config.get(field, "")).strip()]
    if missing:
        raise ValueError(f"checkpoint_store missing fields: {','.join(missing)}")
    api = _checkpoint_api()
    path = Path(str(config["path"]))
    store = api.load_store(path)
    node_id = str(config.get("node_id") or "autonomous-jira-reconciliation")
    item = api.CheckpointInput(
        task_id=str(observation["task_id"]),
        run_id=run_id,
        node_id=node_id,
        repository=str(config["repository"]),
        branch=str(config["branch"]),
        base_sha=str(config["base_sha"]),
        head_sha=str(config["head_sha"]),
        scope_hash=str(config["scope_hash"]),
        state=dict(checkpoint),
        expected_revision=int(store.get("revision", 0)),
        graph_revision=str(config.get("graph_revision")) if config.get("graph_revision") else None,
    )
    updated = api.persist_to_file(path, item)
    readback = api.load_store(path)
    record = api.replay_checkpoint(readback, str(observation["task_id"]), run_id, node_id)
    if not isinstance(record, Mapping) or record.get("state") != dict(checkpoint):
        raise RuntimeError("CHECKPOINT_READBACK_MISMATCH")
    return {
        "checkpoint_persisted": True,
        "checkpoint_store_revision": int(updated.get("revision", 0)),
        "checkpoint_store_digest": updated.get("store_digest"),
    }


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
        "schema_version": "1.0",
        "artifact_type": "autonomous-jira-reconciliation",
        "task_id": task_id,
        "dispatch_id": dispatch_id,
        "canonical_execution_status": canonical,
        "jira_status_before": current,
        "jira_status_intended": intended,
        "jira_status_readback": str(readback) if readback is not None else None,
        "projection_status": projection_status,
        "reason_code": reason_code,
        "canonical_execution_truth_preserved": True,
        "authority_granted": False,
    }
    try:
        persistence = _persist_reconciliation(observation, checkpoint)
    except Exception as exc:
        projection_status = "BLOCKED"
        reason_code = "CHECKPOINT_PERSIST_FAILED"
        synchronized = False
        checkpoint = {**checkpoint, "projection_status": projection_status, "reason_code": reason_code}
        persistence = {
            "checkpoint_persisted": False,
            "checkpoint_store_revision": None,
            "checkpoint_store_digest": None,
            "checkpoint_error": str(exc),
        }
    result = {
        **checkpoint,
        "synchronized": synchronized,
        "late_reconciliation_required": projection_status in {"LATE_RECONCILIATION_REQUIRED", "BLOCKED"},
        "checkpoint": checkpoint,
        **persistence,
    }
    result["reconciliation_digest"] = _digest(result)
    return result
