#!/usr/bin/env python3
"""Deterministic stale-session reconciliation for GWC failure-recovery nodes.

The router receives observed session/checkpoint/lease evidence and returns a
bounded continuation decision. Stale observations never advance work directly;
they supersede, reconcile, or require human review.
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


def decide_stale_session_reconciliation(*, task_id: str, repository: str, branch: str, base_sha: str, head_sha: str, scope_hash: str, session_id: str, observed_owner: str, canonical_owner: str, observed_checkpoint_rev: int, canonical_checkpoint_rev: int, lease_status: str, working_tree_status: str, pending_action_status: str, observed_at: str | None = None) -> dict[str, Any]:
    stale_owner = observed_owner != canonical_owner
    stale_checkpoint = observed_checkpoint_rev < canonical_checkpoint_rev
    future_checkpoint = observed_checkpoint_rev > canonical_checkpoint_rev

    if future_checkpoint:
        outcome, reason = "HUMAN_REQUIRED", "OBSERVED_CHECKPOINT_AHEAD_OF_CANONICAL"
    elif lease_status not in {"ACTIVE", "EXPIRED", "MISSING"}:
        outcome, reason = "RECONCILE", "UNSUPPORTED_LEASE_STATUS"
    elif working_tree_status not in {"CLEAN", "DIRTY", "UNKNOWN"}:
        outcome, reason = "RECONCILE", "UNSUPPORTED_WORKING_TREE_STATUS"
    elif pending_action_status not in {"NONE", "PENDING", "UNKNOWN", "COMMITTED"}:
        outcome, reason = "RECONCILE", "UNSUPPORTED_PENDING_ACTION_STATUS"
    elif stale_owner or stale_checkpoint or lease_status in {"EXPIRED", "MISSING"}:
        outcome, reason = "SUPERSEDE", "STALE_SESSION_OR_CHECKPOINT"
    elif working_tree_status != "CLEAN":
        outcome, reason = "RECONCILE", "WORKING_TREE_NOT_CLEAN"
    elif pending_action_status == "COMMITTED":
        outcome, reason = "HUMAN_REQUIRED", "PENDING_ACTION_ALREADY_COMMITTED"
    elif pending_action_status in {"PENDING", "UNKNOWN"}:
        outcome, reason = "RECONCILE", "PENDING_ACTION_REQUIRES_READBACK"
    else:
        outcome, reason = "CONTINUE", "SESSION_CURRENT"

    decision = {
        "schema_version": "1.0",
        "artifact_type": "stale-session-reconciliation-decision",
        "task_id": task_id,
        "repository": repository,
        "branch": branch,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "scope_hash": scope_hash,
        "session_id": session_id,
        "observed_owner": observed_owner,
        "canonical_owner": canonical_owner,
        "observed_checkpoint_rev": observed_checkpoint_rev,
        "canonical_checkpoint_rev": canonical_checkpoint_rev,
        "lease_status": lease_status,
        "working_tree_status": working_tree_status,
        "pending_action_status": pending_action_status,
        "observed_at": observed_at or _now(),
        "stale_owner": stale_owner,
        "stale_checkpoint": stale_checkpoint,
        "outcome": outcome,
        "reason_code": reason,
        "advance_allowed": outcome == "CONTINUE",
        "checkpoint_required": outcome in {"SUPERSEDE", "RECONCILE", "HUMAN_REQUIRED"},
    }
    decision["decision_digest"] = digest_payload({k: v for k, v in decision.items() if k != "decision_digest"})
    return decision


def is_replay_equivalent(first: dict[str, Any], second: dict[str, Any]) -> bool:
    def stable(payload: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in payload.items() if k not in {"observed_at", "decision_digest"}}
    return digest_payload(stable(first)) == digest_payload(stable(second))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Route stale-session reconciliation from evidence JSON.")
    parser.add_argument("--payload", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(decide_stale_session_reconciliation(**json.loads(args.payload)), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
