#!/usr/bin/env python3
"""Deterministic CAS mismatch recovery for GWC failure-recovery nodes.

The router reloads newer checkpoint state after compare-and-swap mismatch and
chooses deterministic retry/replan/block behavior. It never overwrites newer
state, never performs a blind retry, and denies stale writers (fence mismatch)
from clobbering newer canonical state.

Family invariants (SCRUM-365 / NA81):
  CAS_MISMATCH => AUTHORITATIVE_REREAD_BEFORE_NEXT_WRITE
  RECOVERY_MUST_NOT_EXPAND_SCOPE_OR_AUTHORITY
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


def decide_cas_mismatch_recovery(
    *,
    task_id: str,
    repository: str,
    branch: str,
    base_sha: str,
    head_sha: str,
    scope_hash: str,
    checkpoint_id: str,
    expected_revision: int,
    observed_revision: int,
    reload_status: str,
    pending_action_status: str,
    retry_count: int,
    max_retries: int,
    observed_at: str | None = None,
    actor_id: str | None = None,
    expected_actor_id: str | None = None,
    fence_token: str | None = None,
    expected_fence_token: str | None = None,
    plan_status: str = "CURRENT",
) -> dict[str, Any]:
    # Deterministic routing. Stale-writer denial takes precedence over revision
    # logic: a stale actor (or mismatched fence) MUST NOT overwrite newer canonical
    # state, regardless of the observed revision.
    stale_writer = (
        (actor_id is not None and expected_actor_id is not None and actor_id != expected_actor_id)
        or (fence_token is not None and expected_fence_token is not None and fence_token != expected_fence_token)
    )
    if stale_writer:
        outcome, reason = "STALE_WRITER_DENIED", "STALE_WRITER_MUST_NOT_OVERWRITE_NEWER_STATE"
    elif observed_revision < expected_revision:
        outcome, reason = "HUMAN_REQUIRED", "OBSERVED_REVISION_REGRESSED"
    elif observed_revision == expected_revision:
        outcome, reason = "NO_MISMATCH", "REVISION_MATCHED"
    elif reload_status != "VERIFIED":
        # Authoritative re-read required before any next write.
        outcome, reason = "RELOAD", "NEWER_REVISION_RELOAD_REQUIRED"
    elif plan_status == "STALE":
        # Authoritative re-read succeeded, but the plan built on stale state must be
        # deterministically re-planned rather than blindly retried.
        outcome, reason = "REPLAN", "PLAN_STALE_REQUIRES_REPLAN"
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

    # Invariant: any non-NO_MISMATCH outcome routes through an authoritative re-read
    # (or is denied) before any write; blind overwrite is never permitted.
    authoritative_reread_required = outcome != "NO_MISMATCH"
    checkpoint_required = outcome in {
        "RELOAD",
        "RECONCILE",
        "REPLAN",
        "RETRY_AFTER_RELOAD",
        "HUMAN_REQUIRED",
        "STALE_WRITER_DENIED",
    }
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
        "authoritative_reread_required": authoritative_reread_required,
        "stale_writer_denied": outcome == "STALE_WRITER_DENIED",
        "checkpoint_required": checkpoint_required,
    }
    if actor_id is not None:
        decision["actor_id"] = actor_id
    if expected_actor_id is not None:
        decision["expected_actor_id"] = expected_actor_id
    if fence_token is not None:
        decision["fence_token"] = fence_token
    if expected_fence_token is not None:
        decision["expected_fence_token"] = expected_fence_token
    if plan_status != "CURRENT":
        decision["plan_status"] = plan_status
    decision["decision_digest"] = digest_payload(
        {k: v for k, v in decision.items() if k != "decision_digest"}
    )
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
