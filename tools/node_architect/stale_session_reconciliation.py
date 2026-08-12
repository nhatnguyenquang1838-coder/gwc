#!/usr/bin/env python3
"""Deterministic stale-session reconciliation for GWC failure-recovery nodes.

The router receives observed session/checkpoint/lease evidence and returns a
bounded continuation decision. Stale observations never advance work directly;
they supersede, reconcile, or require human review.

Outcomes
--------
* CONTINUE       - session/checkpoint/lease all current; safe to advance.
* SUPERSEDE      - observed state is stale vs canonical (owner, checkpoint,
                   base/head, or expired/missing lease). A safe rebind to the
                   canonical owner/checkpoint is permitted.
* RECONCILE      - foreign dirty state, unsupported status, or a pending action
                   that must be read back before continuation.
* HUMAN_REQUIRED - observed checkpoint ahead of canonical (divergence) or a
                   pending action already committed.

Family invariant: canonical repo/task/lease/checkpoint state wins over local
session observations; recovery never widens scope or authority.
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


def decide_stale_session_reconciliation(*, task_id: str, repository: str, branch: str, base_sha: str, head_sha: str, scope_hash: str, session_id: str, observed_owner: str, canonical_owner: str, observed_checkpoint_rev: int, canonical_checkpoint_rev: int, lease_status: str, working_tree_status: str, pending_action_status: str, observed_at: str | None = None, observed_base_sha: str | None = None, canonical_base_sha: str | None = None, observed_head_sha: str | None = None, canonical_head_sha: str | None = None) -> dict[str, Any]:
    stale_owner = observed_owner != canonical_owner
    stale_checkpoint = observed_checkpoint_rev < canonical_checkpoint_rev
    future_checkpoint = observed_checkpoint_rev > canonical_checkpoint_rev
    stale_base = bool(observed_base_sha is not None and canonical_base_sha is not None and observed_base_sha != canonical_base_sha)
    stale_head = bool(observed_head_sha is not None and canonical_head_sha is not None and observed_head_sha != canonical_head_sha)

    if future_checkpoint:
        outcome, reason = "HUMAN_REQUIRED", "OBSERVED_CHECKPOINT_AHEAD_OF_CANONICAL"
    elif lease_status not in {"ACTIVE", "EXPIRED", "MISSING"}:
        outcome, reason = "RECONCILE", "UNSUPPORTED_LEASE_STATUS"
    elif working_tree_status not in {"CLEAN", "DIRTY", "UNKNOWN"}:
        outcome, reason = "RECONCILE", "UNSUPPORTED_WORKING_TREE_STATUS"
    elif pending_action_status not in {"NONE", "PENDING", "UNKNOWN", "COMMITTED"}:
        outcome, reason = "RECONCILE", "UNSUPPORTED_PENDING_ACTION_STATUS"
    elif stale_owner or stale_checkpoint or stale_base or stale_head or lease_status in {"EXPIRED", "MISSING"}:
        outcome, reason = "SUPERSEDE", "STALE_SESSION_OR_CHECKPOINT"
    elif working_tree_status != "CLEAN":
        outcome, reason = "RECONCILE", "WORKING_TREE_NOT_CLEAN"
    elif pending_action_status == "COMMITTED":
        outcome, reason = "HUMAN_REQUIRED", "PENDING_ACTION_ALREADY_COMMITTED"
    elif pending_action_status in {"PENDING", "UNKNOWN"}:
        outcome, reason = "RECONCILE", "PENDING_ACTION_REQUIRES_READBACK"
    else:
        outcome, reason = "CONTINUE", "SESSION_CURRENT"

    # A stale session may be safely rebound to the canonical owner/checkpoint
    # once superseded; the caller must never trust the stale local observation.
    rebind_to_canonical = outcome == "SUPERSEDE"

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
        "observed_base_sha": observed_base_sha,
        "canonical_base_sha": canonical_base_sha,
        "observed_head_sha": observed_head_sha,
        "canonical_head_sha": canonical_head_sha,
        "observed_at": observed_at or _now(),
        "stale_owner": stale_owner,
        "stale_checkpoint": stale_checkpoint,
        "stale_base": stale_base,
        "stale_head": stale_head,
        "outcome": outcome,
        "reason_code": reason,
        "advance_allowed": outcome == "CONTINUE",
        "rebind_to_canonical": rebind_to_canonical,
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
