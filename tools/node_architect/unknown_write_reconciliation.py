#!/usr/bin/env python3
"""Deterministic unknown-write reconciliation for GWC failure-recovery nodes.

The router requires provider readback before retrying or accepting an ambiguous
write. Unknown external effects never produce blind retry or PASS.
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


def decide_unknown_write_reconciliation(*, task_id: str, repository: str, branch: str, base_sha: str, head_sha: str, scope_hash: str, operation_id: str, provider_readback_status: str, external_effect_status: str, idempotency_key: str, retry_count: int, max_retries: int, pending_action_recorded: bool, observed_at: str | None = None) -> dict[str, Any]:
    if not pending_action_recorded:
        outcome, reason = "RECONCILE", "PENDING_ACTION_EVIDENCE_MISSING"
    elif provider_readback_status != "VERIFIED":
        outcome, reason = "RECONCILE", "PROVIDER_READBACK_NOT_VERIFIED"
    elif external_effect_status == "UNKNOWN":
        outcome, reason = "RECONCILE", "UNKNOWN_EXTERNAL_EFFECT"
    elif external_effect_status == "COMMITTED":
        outcome, reason = "HUMAN_REQUIRED", "WRITE_ALREADY_COMMITTED"
    elif external_effect_status == "FAILED":
        outcome, reason = "FAIL", "READBACK_CONFIRMED_FAILURE"
    elif external_effect_status == "ZERO_EFFECT" and retry_count < max_retries:
        outcome, reason = "BOUNDED_RETRY", "ZERO_EFFECT_WITH_RETRY_BUDGET"
    elif external_effect_status == "ZERO_EFFECT":
        outcome, reason = "FAIL", "RETRY_BUDGET_EXHAUSTED"
    else:
        outcome, reason = "RECONCILE", "UNSUPPORTED_EFFECT_STATUS"

    decision = {
        "schema_version": "1.0",
        "artifact_type": "unknown-write-reconciliation-decision",
        "task_id": task_id,
        "repository": repository,
        "branch": branch,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "scope_hash": scope_hash,
        "operation_id": operation_id,
        "provider_readback_status": provider_readback_status,
        "external_effect_status": external_effect_status,
        "idempotency_key": idempotency_key,
        "retry_count": retry_count,
        "max_retries": max_retries,
        "pending_action_recorded": pending_action_recorded,
        "observed_at": observed_at or _now(),
        "outcome": outcome,
        "reason_code": reason,
        "blind_retry_allowed": False,
        "pass_allowed": outcome == "BOUNDED_RETRY" or external_effect_status == "COMMITTED",
        "checkpoint_required": outcome in {"BOUNDED_RETRY", "RECONCILE", "HUMAN_REQUIRED"},
    }
    decision["decision_digest"] = digest_payload({k: v for k, v in decision.items() if k != "decision_digest"})
    return decision


def is_replay_equivalent(first: dict[str, Any], second: dict[str, Any]) -> bool:
    def stable(payload: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in payload.items() if k not in {"observed_at", "decision_digest"}}
    return digest_payload(stable(first)) == digest_payload(stable(second))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Route unknown-write reconciliation from readback evidence JSON.")
    parser.add_argument("--payload", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(decide_unknown_write_reconciliation(**json.loads(args.payload)), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
