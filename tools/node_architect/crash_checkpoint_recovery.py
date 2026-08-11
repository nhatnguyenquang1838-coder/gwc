#!/usr/bin/env python3
"""Deterministic crash checkpoint recovery routing for GWC failure-recovery nodes.

The router makes no external calls. It receives canonical checkpoint and
pending-action evidence produced by a caller and returns a bounded recovery
decision. Crash resume never creates a duplicate effect unless the checkpoint
and readback evidence prove it is safe to continue.
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


def decide_crash_checkpoint_recovery(
    *,
    task_id: str,
    repository: str,
    branch: str,
    base_sha: str,
    head_sha: str,
    scope_hash: str,
    run_id: str,
    checkpoint_id: str,
    checkpoint_revision: int,
    checkpoint_status: str,
    pending_action_status: str,
    readback_status: str,
    effect_status: str,
    idempotency_key: str,
    resume_token: str,
    observed_at: str | None = None,
    observed_head_sha: str | None = None,
) -> dict[str, Any]:
    """Return a deterministic post-crash recovery decision."""

    if not resume_token:
        outcome, reason = "BLOCKED", "MISSING_RESUME_TOKEN"
    elif not head_sha:
        outcome, reason = "BLOCKED", "MISSING_HEAD_SHA"
    elif not checkpoint_id:
        outcome, reason = "BLOCKED", "INVALID_CHECKPOINT_ID"
    elif observed_head_sha is not None and observed_head_sha != head_sha:
        outcome, reason = "RECONCILE", "HEAD_DRIFT"
    elif checkpoint_status == "PARTIAL":
        outcome, reason = "RECONCILE", "PARTIAL_CHECKPOINT"
    elif checkpoint_status != "CANONICAL":
        outcome, reason = "RECONCILE", "CHECKPOINT_NOT_CANONICAL"
    elif checkpoint_revision < 0:
        outcome, reason = "FAIL", "INVALID_CHECKPOINT_REVISION"
    elif readback_status != "VERIFIED":
        outcome, reason = "RECONCILE", "READBACK_NOT_VERIFIED"
    elif pending_action_status == "NONE":
        outcome, reason = "RESUME", "NO_PENDING_ACTION"
    elif pending_action_status == "COMPLETED":
        outcome, reason = "RESUME", "PENDING_ACTION_ALREADY_COMPLETED"
    elif pending_action_status == "IN_FLIGHT" and effect_status == "ZERO_EFFECT":
        outcome, reason = "RESUME", "PENDING_ACTION_ZERO_EFFECT"
    elif pending_action_status == "IN_FLIGHT" and effect_status == "UNKNOWN":
        outcome, reason = "RECONCILE", "UNKNOWN_EXTERNAL_EFFECT_AFTER_CRASH"
    elif pending_action_status == "IN_FLIGHT" and effect_status == "COMMITTED":
        outcome, reason = "HUMAN_REQUIRED", "PENDING_ACTION_MAY_HAVE_COMMITTED"
    elif pending_action_status == "IN_FLIGHT" and effect_status == "FAILED":
        outcome, reason = "FAIL", "PENDING_ACTION_CONFIRMED_FAILED"
    elif pending_action_status == "STALE":
        outcome, reason = "RECONCILE", "STALE_PENDING_ACTION"
    elif pending_action_status == "PARTIAL":
        outcome, reason = "RECONCILE", "PARTIAL_CRASH_PENDING_ACTION"
    else:
        outcome, reason = "RECONCILE", "UNSUPPORTED_CRASH_RECOVERY_STATE"

    duplicate_effect_allowed = (
        outcome == "RESUME"
        and readback_status == "VERIFIED"
        and pending_action_status in {"NONE", "COMPLETED", "IN_FLIGHT"}
        and effect_status in {"ZERO_EFFECT", "COMMITTED", "NOT_APPLICABLE"}
        and reason != "PENDING_ACTION_MAY_HAVE_COMMITTED"
    )

    decision = {
        "schema_version": "1.0",
        "artifact_type": "crash-checkpoint-recovery-decision",
        "task_id": task_id,
        "repository": repository,
        "branch": branch,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "scope_hash": scope_hash,
        "run_id": run_id,
        "checkpoint_id": checkpoint_id,
        "checkpoint_revision": checkpoint_revision,
        "checkpoint_status": checkpoint_status,
        "pending_action_status": pending_action_status,
        "readback_status": readback_status,
        "effect_status": effect_status,
        "idempotency_key": idempotency_key,
        "resume_token": resume_token,
        "observed_at": observed_at or _now(),
        "outcome": outcome,
        "reason_code": reason,
        "checkpoint_required": outcome in {"RESUME", "RECONCILE", "HUMAN_REQUIRED", "BLOCKED"},
        "readback_required_before_effect": outcome in {"RESUME", "RECONCILE", "HUMAN_REQUIRED", "BLOCKED"},
        "duplicate_effect_allowed": duplicate_effect_allowed,
    }
    decision["decision_digest"] = digest_payload({k: v for k, v in decision.items() if k != "decision_digest"})
    return decision


def is_replay_equivalent(first: dict[str, Any], second: dict[str, Any]) -> bool:
    def stable(payload: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in payload.items() if k not in {"observed_at", "decision_digest"}}

    return digest_payload(stable(first)) == digest_payload(stable(second))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Route a crash-checkpoint recovery decision from evidence JSON.")
    parser.add_argument("--payload", required=True, help="JSON object with decide_crash_checkpoint_recovery keyword arguments")
    args = parser.parse_args(argv)
    decision = decide_crash_checkpoint_recovery(**json.loads(args.payload))
    print(json.dumps(decision, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
