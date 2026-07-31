#!/usr/bin/env python3
"""Deterministic duplicate-agent fencing for GWC failure-recovery nodes."""
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


def decide_duplicate_agent_fencing(
    *,
    task_id: str,
    repository: str,
    branch: str,
    base_sha: str,
    head_sha: str,
    scope_hash: str,
    run_id: str,
    worker_id: str,
    active_lease_holder: str,
    worker_fencing_token: int,
    observed_fencing_token: int,
    lease_state: str,
    side_effect_key: str,
    committed_side_effect_keys: list[str] | None = None,
    race_detected: bool = False,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Fence duplicate agents and suppress duplicate side effects."""
    committed_side_effect_keys = committed_side_effect_keys or []
    stale_worker = worker_id != active_lease_holder or worker_fencing_token < observed_fencing_token
    duplicate_effect = side_effect_key in set(committed_side_effect_keys)

    outcome = "ALLOW_SINGLE_EFFECT"
    reason_code = "LEASE_HOLDER_AND_FENCE_MATCH"
    advancement_allowed = True
    side_effect_allowed = True
    duplicate_effect_prevented = False

    if lease_state != "ACTIVE":
        outcome = "BLOCK_NO_ACTIVE_LEASE"
        reason_code = "LEASE_NOT_ACTIVE"
        advancement_allowed = False
        side_effect_allowed = False
    elif stale_worker:
        outcome = "FENCE_STALE_WORKER"
        reason_code = "WORKER_NOT_CURRENT_LEASE_HOLDER_OR_TOKEN_STALE"
        advancement_allowed = False
        side_effect_allowed = False
    elif race_detected:
        outcome = "FENCE_DUPLICATE_AGENT"
        reason_code = "DUPLICATE_AGENT_RACE_DETECTED"
        advancement_allowed = False
        side_effect_allowed = False
    elif duplicate_effect:
        outcome = "SUPPRESS_DUPLICATE_EFFECT"
        reason_code = "SIDE_EFFECT_KEY_ALREADY_COMMITTED"
        advancement_allowed = True
        side_effect_allowed = False
        duplicate_effect_prevented = True

    decision = {
        "schema_version": "1.0",
        "artifact_type": "duplicate-agent-fencing-decision",
        "task_id": task_id,
        "repository": repository,
        "branch": branch,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "scope_hash": scope_hash,
        "run_id": run_id,
        "worker_id": worker_id,
        "active_lease_holder": active_lease_holder,
        "worker_fencing_token": worker_fencing_token,
        "observed_fencing_token": observed_fencing_token,
        "lease_state": lease_state,
        "side_effect_key": side_effect_key,
        "committed_side_effect_keys": committed_side_effect_keys,
        "race_detected": race_detected,
        "stale_worker": stale_worker,
        "duplicate_effect": duplicate_effect,
        "fencing_enforced": True,
        "advancement_allowed": advancement_allowed,
        "side_effect_allowed": side_effect_allowed,
        "duplicate_effect_prevented": duplicate_effect_prevented,
        "outcome": outcome,
        "reason_code": reason_code,
        "observed_at": observed_at or now_utc(),
    }
    return attach_digest(decision)
