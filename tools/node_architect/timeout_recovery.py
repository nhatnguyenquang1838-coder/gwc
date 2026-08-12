#!/usr/bin/env python3
"""Deterministic timeout recovery routing for GWC failure-recovery nodes.

The router makes no external calls. It receives readback evidence produced by a
caller and returns one of the bounded outcomes. Unknown external effects never
produce blind redispatch; they route to reconciliation or human review.

Outcomes
--------
* WAIT                 - not timed out, or a real (still in-flight) pending effect
                         that must be polled, never assumed failed.
* RECONCILE            - readback unverified, unknown effect, or an interruption
                         whose external effect is unknown and must be reconciled
                         before any retry (no duplicate effects possible).
* HUMAN_REQUIRED       - effect already committed or a future/foreign conflict.
* BOUNDED_RETRY        - zero effect with retry budget remaining.
* FAIL                 - readback-confirmed failure or exhausted retry budget.

Family invariant: UNKNOWN_EFFECT => READBACK_OR_RECONCILE_BEFORE_RETRY.
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


def decide_timeout_recovery(*, task_id: str, repository: str, branch: str, base_sha: str, head_sha: str, scope_hash: str, operation_id: str, timed_out: bool, readback_status: str, effect_status: str, retry_count: int, max_retries: int, idempotency_key: str, deadline_at: str, observed_at: str | None = None, interruption_detected: bool = False) -> dict[str, Any]:
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
    elif effect_status == "PENDING":
        # A real, still-in-flight pending effect is distinct from a timeout:
        # poll/readback rather than assume failure or blind-redispatch.
        outcome, reason = "WAIT", "REAL_PENDING_AWAIT_READBACK"
    elif effect_status == "ZERO_EFFECT" and retry_count < max_retries:
        outcome, reason = "BOUNDED_RETRY", "ZERO_EFFECT_WITH_RETRY_BUDGET"
    elif effect_status == "ZERO_EFFECT":
        outcome, reason = "FAIL", "RETRY_BUDGET_EXHAUSTED"
    else:
        outcome, reason = "RECONCILE", "UNSUPPORTED_EFFECT_STATUS"

    # An interruption ends the prior attempt abruptly; its external effect is
    # unknown. Before any re-dispatch (bounded retry or pending poll) we must
    # reconcile/readback so a duplicate effect is impossible. Confirmed
    # terminal outcomes (FAIL/COMMITTED/HUMAN) are left untouched.
    if interruption_detected and outcome in {"BOUNDED_RETRY", "WAIT"}:
        outcome, reason = "RECONCILE", "INTERRUPTION_REQUIRES_RECHECK"

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
        "interruption_detected": interruption_detected,
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
