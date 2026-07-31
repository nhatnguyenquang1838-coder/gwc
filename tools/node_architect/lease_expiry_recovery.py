#!/usr/bin/env python3
"""Deterministic lease-expiry recovery for GWC failure-recovery nodes.

The router prevents stale workers from advancing after lease expiry and only
allows continuation after safe readback and monotonic lease reacquisition.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest_payload(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def decide_lease_expiry_recovery(*, task_id: str, repository: str, branch: str, base_sha: str, head_sha: str, scope_hash: str, lease_id: str, worker_id: str, now_epoch_ms: int, lease_expires_epoch_ms: int, observed_fencing_token: int, worker_fencing_token: int, readback_status: str, reacquire_status: str, duplicate_agent_detected: bool, side_effect_status: str, observed_at: str | None = None) -> dict[str, Any]:
    lease_expired = now_epoch_ms >= lease_expires_epoch_ms
    stale_worker = worker_fencing_token < observed_fencing_token

    advancement_allowed = False
    side_effect_allowed = False
    reacquire_required = False
    checkpoint_required = True

    if not lease_expired:
        outcome, reason = "CONTINUE", "LEASE_STILL_VALID"
        advancement_allowed = True
        side_effect_allowed = side_effect_status == "NONE"
        checkpoint_required = False
    elif stale_worker:
        outcome, reason = "FENCE_STALE_WORKER", "WORKER_FENCING_TOKEN_STALE"
    elif readback_status != "VERIFIED_ZERO_EFFECT":
        outcome, reason = "READBACK_REQUIRED", "SAFE_READBACK_REQUIRED_AFTER_EXPIRY"
    elif duplicate_agent_detected:
        outcome, reason = "FENCE_DUPLICATE_AGENT", "DUPLICATE_AGENT_RACE_DETECTED"
    elif side_effect_status in {"COMMITTED", "UNKNOWN", "PENDING"}:
        outcome, reason = "RECONCILE", "SIDE_EFFECT_RECONCILIATION_REQUIRED"
    elif reacquire_status != "REACQUIRED_MONOTONIC":
        outcome, reason = "REACQUIRE_LEASE", "MONOTONIC_REACQUIRE_REQUIRED"
        reacquire_required = True
    else:
        outcome, reason = "CONTINUE_AFTER_REACQUIRE", "LEASE_REACQUIRED_WITH_MONOTONIC_FENCE"
        advancement_allowed = True
        side_effect_allowed = True
        checkpoint_required = False

    decision = {
        "schema_version": "1.0",
        "artifact_type": "lease-expiry-recovery-decision",
        "task_id": task_id,
        "repository": repository,
        "branch": branch,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "scope_hash": scope_hash,
        "lease_id": lease_id,
        "worker_id": worker_id,
        "now_epoch_ms": now_epoch_ms,
        "lease_expires_epoch_ms": lease_expires_epoch_ms,
        "lease_expired": lease_expired,
        "observed_fencing_token": observed_fencing_token,
        "worker_fencing_token": worker_fencing_token,
        "readback_status": readback_status,
        "reacquire_status": reacquire_status,
        "duplicate_agent_detected": duplicate_agent_detected,
        "side_effect_status": side_effect_status,
        "observed_at": observed_at or _now(),
        "outcome": outcome,
        "reason_code": reason,
        "advancement_allowed": advancement_allowed,
        "side_effect_allowed": side_effect_allowed,
        "reacquire_required": reacquire_required,
        "checkpoint_required": checkpoint_required,
        "blind_retry_allowed": False,
    }
    decision["decision_digest"] = digest_payload({k: v for k, v in decision.items() if k != "decision_digest"})
    return decision


def is_replay_equivalent(first: dict[str, Any], second: dict[str, Any]) -> bool:
    def stable(payload: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in payload.items() if k not in {"observed_at", "decision_digest"}}
    return digest_payload(stable(first)) == digest_payload(stable(second))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Route lease expiry recovery from evidence JSON.")
    parser.add_argument("--payload", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(decide_lease_expiry_recovery(**json.loads(args.payload)), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
