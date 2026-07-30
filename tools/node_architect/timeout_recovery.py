#!/usr/bin/env python3
"""Deterministic timeout recovery routing for GWC failure-recovery nodes.

The router makes no external calls. It receives readback evidence produced by a
caller and returns one of the bounded outcomes. Unknown external effects never
produce blind redispatch; they route to reconciliation or human review.
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


def decide_timeout_recovery(*, task_id: str, repository: str, branch: str, base_sha: str, head_sha: str, scope_hash: str, operation_id: str, timed_out: bool, readback_status: str, effect_status: str, retry_count: int, max_retries: int, idempotency_key: str, deadline_at: str, observed_at: str | None = None) -> dict[str, Any]:
    if not timed_out:
        outcome, reason = "WAIT", "NOT_TIMED_OUT"
    elif readback_status != "VERIFIED":
        outcome, reason = "RECONCILE", "READBACK_NOT_VERIFIED"
    elif effect_status == "UNKNOWN":
        outcome, reason = "RECONCILE", "UNKNOWN_EXTERNAL_EFFECT"
    elif effect_status == "COMMITTED":
        outcome, reason = "HUMAN_REQUIRED", "EFFECT_ALREADY_COMMITTED"
    elif effect_status == "FAILED":
        outcome, reason = "FAIL", "READBACK_CONFIRMED_FAILURE"
    elif effect_status == "ZERO_EFFECT" and retry_count < max_retries:
        outcome, reason = "BOUNDED_RETRY", "ZERO_EFFECT_WITH_RETRY_BUDGET"
    elif effect_status == "ZERO_EFFECT":
        outcome, reason = "FAIL", "RETRY_BUDGET_EXHAUSTED"
    else:
        outcome, reason = "RECONCILE", "UNSUPPORTED_EFFECT_STATUS"

    decision = {
        "schema_version": "1.0",
        "artifact_type": "timeout-recovery-decision",
        "task_id": task_id,
        "repository": repository,
        "branch": branch,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "scope_hash": scope_hash,
        "operation_id": operation_id,
        "timed_out": timed_out,
        "readback_status": readback_status,
        "effect_status": effect_status,
        "retry_count": retry_count,
        "max_retries": max_retries,
        "idempotency_key": idempotency_key,
        "deadline_at": deadline_at,
        "observed_at": observed_at or _now(),
        "outcome": outcome,
        "reason_code": reason,
        "blind_redispatch_allowed": False,
        "checkpoint_required": outcome in {"WAIT", "BOUNDED_RETRY", "RECONCILE", "HUMAN_REQUIRED"},
    }
    decision["decision_digest"] = digest_payload({k: v for k, v in decision.items() if k != "decision_digest"})
    return decision


def is_replay_equivalent(first: dict[str, Any], second: dict[str, Any]) -> bool:
    def stable(payload: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in payload.items() if k not in {"observed_at", "decision_digest"}}
    return digest_payload(stable(first)) == digest_payload(stable(second))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Route a timeout recovery decision from readback evidence JSON.")
    parser.add_argument("--payload", required=True, help="JSON object with decide_timeout_recovery keyword arguments")
    args = parser.parse_args(argv)
    decision = decide_timeout_recovery(**json.loads(args.payload))
    print(json.dumps(decision, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
