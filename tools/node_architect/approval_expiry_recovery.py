#!/usr/bin/env python3
"""Deterministic approval-expiry recovery for GWC failure-recovery nodes."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest_payload(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def attach_digest(decision: dict[str, Any]) -> dict[str, Any]:
    decision["decision_digest"] = digest_payload({k: v for k, v in decision.items() if k != "decision_digest"})
    return decision


def decide_approval_expiry_recovery(
    *,
    task_id: str,
    repository: str,
    branch: str,
    base_sha: str,
    head_sha: str,
    approval_id: str,
    approval_scope_hash: str,
    current_scope_hash: str,
    approval_expires_at: str,
    now_at: str,
    continuation_requested: bool,
    checkpoint_digest_before_wait: str | None,
    current_checkpoint_digest: str | None,
    replay_nonce: str,
    consumed_replay_nonces: list[str] | None = None,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Route approval expiry/replay recovery without stale continuation."""
    consumed_replay_nonces = consumed_replay_nonces or []
    expired = parse_utc(now_at) >= parse_utc(approval_expires_at)
    scope_drifted = approval_scope_hash != current_scope_hash
    replay_detected = replay_nonce in set(consumed_replay_nonces)
    checkpoint_missing = not checkpoint_digest_before_wait or not current_checkpoint_digest
    checkpoint_mismatch = (
        checkpoint_digest_before_wait is not None
        and current_checkpoint_digest is not None
        and checkpoint_digest_before_wait != current_checkpoint_digest
    )

    outcome = "CONTINUE"
    reason_code = "APPROVAL_VALID_AND_CHECKPOINT_CURRENT"
    regenerate_approval_required = False
    replay_rejected = False
    checkpoint_required = False
    wait_allowed = True
    continuation_allowed = True

    if replay_detected:
        outcome = "REJECT_REPLAY"
        reason_code = "REPLAY_NONCE_ALREADY_CONSUMED"
        replay_rejected = True
        wait_allowed = False
        continuation_allowed = False
    elif expired:
        outcome = "REGENERATE_APPROVAL"
        reason_code = "APPROVAL_EXPIRED"
        regenerate_approval_required = True
        wait_allowed = False
        continuation_allowed = False
    elif scope_drifted:
        outcome = "REGENERATE_APPROVAL"
        reason_code = "APPROVAL_SCOPE_HASH_DRIFTED"
        regenerate_approval_required = True
        wait_allowed = False
        continuation_allowed = False
    elif continuation_requested and checkpoint_missing:
        outcome = "CHECKPOINT_BEFORE_WAIT"
        reason_code = "CHECKPOINT_REQUIRED_BEFORE_WAIT"
        checkpoint_required = True
        wait_allowed = False
        continuation_allowed = False
    elif continuation_requested and checkpoint_mismatch:
        outcome = "REGENERATE_APPROVAL"
        reason_code = "CHECKPOINT_DRIFTED_DURING_WAIT"
        regenerate_approval_required = True
        wait_allowed = False
        continuation_allowed = False

    decision = {
        "schema_version": "1.0",
        "artifact_type": "approval-expiry-recovery-decision",
        "task_id": task_id,
        "repository": repository,
        "branch": branch,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "approval_id": approval_id,
        "approval_scope_hash": approval_scope_hash,
        "current_scope_hash": current_scope_hash,
        "approval_expires_at": approval_expires_at,
        "now_at": now_at,
        "approval_expired": expired,
        "scope_drifted": scope_drifted,
        "continuation_requested": continuation_requested,
        "checkpoint_digest_before_wait": checkpoint_digest_before_wait,
        "current_checkpoint_digest": current_checkpoint_digest,
        "checkpoint_required": checkpoint_required,
        "checkpoint_mismatch": checkpoint_mismatch,
        "replay_nonce": replay_nonce,
        "replay_detected": replay_detected,
        "replay_rejected": replay_rejected,
        "regenerate_approval_required": regenerate_approval_required,
        "wait_allowed": wait_allowed,
        "continuation_allowed": continuation_allowed,
        "stale_continuation_allowed": False,
        "outcome": outcome,
        "reason_code": reason_code,
        "observed_at": observed_at or now_utc(),
    }
    return attach_digest(decision)


def replay_safe(first: dict[str, Any], second: dict[str, Any]) -> bool:
    ignored = {"observed_at", "decision_digest"}
    return digest_payload({k: v for k, v in first.items() if k not in ignored}) == digest_payload(
        {k: v for k, v in second.items() if k not in ignored}
    )
