#!/usr/bin/env python3
"""Deterministic CAS mismatch recovery for GWC failure-recovery nodes.

The router reloads newer checkpoint state after compare-and-swap mismatch.
It never overwrites newer state or blindly retries after concurrent changes.
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


def decide_cas_mismatch_recovery(*, task_id: str, repository: str, branch: str, base_sha: str, head_sha: str, scope_hash: str, checkpoint_id: str, expected_revision: int, observed_revision: int, reload_status: str, pending_action_status: str, retry_count: int, max_retries: int, observed_at: str | None = None) -> dict[str, Any]:
    if observed_revision < expected_revision:
        outcome, reason = "HUMAN_REQUIRED", "OBSERVED_REVISION_REGRESSED"
    elif observed_revision == expected_revision:
        outcome, reason = "NO_MISMATCH", "REVISION_MATCHED"
    elif reload_status != "VERIFIED":
        outcome, reason = "RELOAD", "NEWER_REVISION_RELOAD_REQUIRED"
    elif pending_action_status in {"UNKNOWN", "PENDING"}:
        outcome, reason = "RECONCILE", "PENDING_ACTION_REQUIRES_READBACK"
    elif pending_action_status == "COMMITTED":
        outcome, reason = "HUMAN_REQUIRED", "PENDING_ACTION_ALREADY_COMMITTED"
    elif pending_action_status == "NONE" and retry_count < max_retries:
        outcome, reason = "RETRY_AFTER_RELOAD", "NEWER_REVISION_VERIFIED_WITH_RETRY_BUDGET"
    elif pending_action_status == "NONE":
        outcome, reason = "FAIL", "RETRY_BUDGET_EXHAUSTED"
    else:
        outcome, reason = "RECONCILE", "UNSUPPORTED_PENDING_ACTION_STATUS"

    decision = {
        "schema_version": "1.0",
        "artifact_type": "cas-mismatch-recovery-decision",
        "task_id": task_id,
        "repository": repository,
        "branch": branch,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "scope_hash": scope_hash,
        "checkpoint_id": checkpoint_id,
        "expected_revision": expected_revision,
        "observed_revision": observed_revision,
        "reload_status": reload_status,
        "pending_action_status": pending_action_status,
        "retry_count": retry_count,
        "max_retries": max_retries,
        "observed_at": observed_at or _now(),
        "outcome": outcome,
        "reason_code": reason,
        "overwrite_allowed": False,
        "blind_retry_allowed": False,
        "checkpoint_required": outcome in {"RELOAD", "RECONCILE", "RETRY_AFTER_RELOAD", "HUMAN_REQUIRED"},
    }
    decision["decision_digest"] = digest_payload({k: v for k, v in decision.items() if k != "decision_digest"})
    return decision


def is_replay_equivalent(first: dict[str, Any], second: dict[str, Any]) -> bool:
    def stable(payload: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in payload.items() if k not in {"observed_at", "decision_digest"}}
    return digest_payload(stable(first)) == digest_payload(stable(second))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Route CAS mismatch recovery from checkpoint evidence JSON.")
    parser.add_argument("--payload", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(decide_cas_mismatch_recovery(**json.loads(args.payload)), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
