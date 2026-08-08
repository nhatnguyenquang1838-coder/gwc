#!/usr/bin/env python3
"""Reconcile an autonomous run after interruption or unknown external effect.

Builds on the deterministic checkpoint primitives and duplicate-agent fencing
used by the runtime. For a given checkpoint + readback, it returns a bounded
decision: RESUME (safe to continue, no duplicate effect), RECONCILE (perform
readback before retry), or HUMAN_REQUIRED (possible committed effect). This is a
pure, local decision function; it never performs the side effect itself.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .autonomous_run_checkpoint import AutonomousRunCheckpoint
from .duplicate_agent_fencing import decide_duplicate_agent_fencing


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def reconcile_autonomous_run(
    *,
    task_id: str,
    repository: str,
    branch: str,
    base_sha: str,
    head_sha: str,
    scope_hash: str,
    run_id: str,
    checkpoint: AutonomousRunCheckpoint,
    readback_status: str,
    effect_status: str,
    worker_id: str,
    active_lease_holder: str,
    worker_fencing_token: int,
    observed_fencing_token: int,
    lease_state: str,
    committed_side_effect_keys: list[str] | None = None,
    race_detected: bool = False,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Determine whether an autonomous run may RESUME without a duplicate effect.

    Returns a deterministic reconciliation decision. RESUME means the run can
    continue from the latest valid checkpoint; RECONCILE means readback must be
    performed before retrying; HUMAN_REQUIRED means a side effect may already
    have committed and a human must adjudicate.
    """
    if checkpoint is None or not isinstance(checkpoint, AutonomousRunCheckpoint):
        return {
            "schema_version": "1.0",
            "artifact_type": "autonomous-run-reconciliation",
            "task_id": task_id,
            "run_id": run_id,
            "outcome": "RECONCILE",
            "reason_code": "CHECKPOINT_MISSING",
            "duplicate_effect_prevented": False,
            "advancement_allowed": False,
            "authority_granted": False,
            "observed_at": observed_at or now_utc(),
        }

    if checkpoint.checkpoint_key != f"{task_id}:{run_id}:{checkpoint.manifest_digest_value}":
        return {
            "schema_version": "1.0",
            "artifact_type": "autonomous-run-reconciliation",
            "task_id": task_id,
            "run_id": run_id,
            "outcome": "RECONCILE",
            "reason_code": "CHECKPOINT_BINDING_MISMATCH",
            "duplicate_effect_prevented": False,
            "advancement_allowed": False,
            "authority_granted": False,
            "observed_at": observed_at or now_utc(),
        }

    fence = decide_duplicate_agent_fencing(
        task_id=task_id,
        repository=repository,
        branch=branch,
        base_sha=base_sha,
        head_sha=head_sha,
        scope_hash=scope_hash,
        run_id=run_id,
        worker_id=worker_id,
        active_lease_holder=active_lease_holder,
        worker_fencing_token=worker_fencing_token,
        observed_fencing_token=observed_fencing_token,
        lease_state=lease_state,
        side_effect_key=checkpoint.checkpoint_key,
        committed_side_effect_keys=committed_side_effect_keys,
        race_detected=race_detected,
        observed_at=observed_at,
    )

    if fence["outcome"] in ("FENCE_STALE_WORKER", "FENCE_DUPLICATE_AGENT", "BLOCK_NO_ACTIVE_LEASE"):
        return {
            "schema_version": "1.0",
            "artifact_type": "autonomous-run-reconciliation",
            "task_id": task_id,
            "run_id": run_id,
            "outcome": "RECONCILE",
            "reason_code": "FENCING_" + fence["reason_code"],
            "fence_outcome": fence["outcome"],
            "duplicate_effect_prevented": True,
            "advancement_allowed": False,
            "authority_granted": False,
            "observed_at": observed_at or now_utc(),
        }

    if fence["outcome"] == "SUPPRESS_DUPLICATE_EFFECT":
        return {
            "schema_version": "1.0",
            "artifact_type": "autonomous-run-reconciliation",
            "task_id": task_id,
            "run_id": run_id,
            "outcome": "RESUME",
            "reason_code": "DUPLICATE_EFFECT_SUPPRESSED",
            "fence_outcome": fence["outcome"],
            "duplicate_effect_prevented": True,
            "advancement_allowed": True,
            "authority_granted": False,
            "observed_at": observed_at or now_utc(),
        }

    if effect_status == "UNKNOWN":
        return {
            "schema_version": "1.0",
            "artifact_type": "autonomous-run-reconciliation",
            "task_id": task_id,
            "run_id": run_id,
            "outcome": "RECONCILE",
            "reason_code": "UNKNOWN_EXTERNAL_EFFECT_REQUIRES_READBACK",
            "readback_status": readback_status,
            "duplicate_effect_prevented": False,
            "advancement_allowed": False,
            "authority_granted": False,
            "observed_at": observed_at or now_utc(),
        }

    if effect_status == "COMMITTED":
        return {
            "schema_version": "1.0",
            "artifact_type": "autonomous-run-reconciliation",
            "task_id": task_id,
            "run_id": run_id,
            "outcome": "HUMAN_REQUIRED",
            "reason_code": "POSSIBLE_COMMITTED_EFFECT",
            "readback_status": readback_status,
            "duplicate_effect_prevented": False,
            "advancement_allowed": False,
            "authority_granted": False,
            "observed_at": observed_at or now_utc(),
        }

    # ZERO_EFFECT / NOT_APPLICABLE / NONE -> safe to resume.
    return {
        "schema_version": "1.0",
        "artifact_type": "autonomous-run-reconciliation",
        "task_id": task_id,
        "run_id": run_id,
        "outcome": "RESUME",
        "reason_code": "SAFE_TO_RESUME",
        "readback_status": readback_status,
        "effect_status": effect_status,
        "duplicate_effect_prevented": False,
        "advancement_allowed": True,
        "authority_granted": False,
        "observed_at": observed_at or now_utc(),
    }


__all__ = ["reconcile_autonomous_run"]
