#!/usr/bin/env python3
"""Deterministic version-drift rollback routing for GWC failure-recovery nodes."""
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
    decision["decision_digest"] = digest_payload({k: v for k, v in decision.items() if k != "decision_digest"})
    return decision


def _valid_non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def decide_version_drift_rollback_routing(
    *,
    task_id: str,
    repository: str,
    branch: str,
    base_sha: str,
    head_sha: str,
    scope_hash: str,
    run_id: str,
    checkpoint_id: str,
    snapshot_node_version: str,
    runtime_node_version: str,
    compatibility_rule: str,
    replay_requested: bool,
    replay_epoch: int,
    current_epoch: int,
    rollback_evidence_digest: str | None,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Route node-version drift while preserving evidence and G5 boundaries."""
    drift_detected = snapshot_node_version != runtime_node_version
    stale_replay = replay_requested and replay_epoch < current_epoch
    evidence_preserved = bool(rollback_evidence_digest)
    g5_manual_action_authorized = False

    outcome = "CONTINUE"
    reason_code = "NODE_VERSION_MATCH"
    replay_allowed = True
    new_epoch_required = False
    governed_repair_required = False
    rollback_route_required = False

    version_evidence_unavailable = not (
        _valid_non_empty(snapshot_node_version) and _valid_non_empty(runtime_node_version)
    )

    if version_evidence_unavailable:
        outcome = "BLOCK_UNSUPPORTED_DRIFT"
        reason_code = "VERSION_EVIDENCE_UNAVAILABLE"
        replay_allowed = False
        governed_repair_required = True
    elif stale_replay:
        outcome = "REJECT_STALE_REPLAY"
        reason_code = "REPLAY_EPOCH_BEHIND_CURRENT_EPOCH"
        replay_allowed = False
    elif not drift_detected:
        outcome = "CONTINUE"
        reason_code = "NODE_VERSION_MATCH"
    elif compatibility_rule == "COMPATIBLE":
        outcome = "CONTINUE_COMPATIBLE"
        reason_code = "DRIFT_MARKED_COMPATIBLE"
    elif compatibility_rule == "NEW_EPOCH_REQUIRED":
        outcome = "ROUTE_NEW_EPOCH"
        reason_code = "DRIFT_REQUIRES_NEW_EPOCH"
        new_epoch_required = True
    elif compatibility_rule == "GOVERNED_REPAIR_REQUIRED":
        outcome = "ROUTE_GOVERNED_REPAIR"
        reason_code = "DRIFT_REQUIRES_GOVERNED_REPAIR"
        governed_repair_required = True
    elif compatibility_rule == "ROLLBACK_REQUIRED":
        outcome = "ROUTE_ROLLBACK_EVIDENCE"
        reason_code = "DRIFT_REQUIRES_ROLLBACK_EVIDENCE_ROUTE"
        rollback_route_required = True
        governed_repair_required = True
    else:
        outcome = "BLOCK_UNSUPPORTED_DRIFT"
        reason_code = "NO_COMPATIBILITY_RULE_FOR_DRIFT"
        replay_allowed = False
        governed_repair_required = True

    decision = {
        "schema_version": "1.0",
        "artifact_type": "version-drift-rollback-routing-decision",
        "task_id": task_id,
        "repository": repository,
        "branch": branch,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "scope_hash": scope_hash,
        "run_id": run_id,
        "checkpoint_id": checkpoint_id,
        "snapshot_node_version": snapshot_node_version,
        "runtime_node_version": runtime_node_version,
        "drift_detected": drift_detected,
        "compatibility_rule": compatibility_rule,
        "replay_requested": replay_requested,
        "replay_epoch": replay_epoch,
        "current_epoch": current_epoch,
        "stale_replay": stale_replay,
        "replay_allowed": replay_allowed,
        "new_epoch_required": new_epoch_required,
        "governed_repair_required": governed_repair_required,
        "rollback_route_required": rollback_route_required,
        "rollback_evidence_digest": rollback_evidence_digest,
        "evidence_preserved": evidence_preserved,
        "g5_manual_action_authorized": g5_manual_action_authorized,
        "version_evidence_unavailable": version_evidence_unavailable,
        "outcome": outcome,
        "reason_code": reason_code,
        "observed_at": observed_at or now_utc(),
    }
    return attach_digest(decision)
