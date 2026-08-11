#!/usr/bin/env python3
"""Deterministic lease-acquisition decision utility for GWC runtime checkpoint nodes.

Implements the ``runtime_checkpoint.lease-acquisition`` node (MAT-F4-N05).
This module is local and data-oriented. It does not call GitHub, Jira, Slack,
or production services. Callers pass already-authorized task, repository, gate,
and scope data; the decision utility evaluates competing-lease evidence and
returns a monotonic fencing token when acquisition is allowed.

Design:
- ``decide_lease_acquisition`` is a pure function: identical inputs produce
  identical outputs.
- Fail-closed on missing/ambiguous binding or unknown gate identity.
- Persistence of the acquired lease remains the caller's responsibility via
  ``checkpoint_store.py``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from .checkpoint_store import canonical_json, digest_payload


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


_REQUIRED_BINDING = (
    "task_id",
    "run_id",
    "node_id",
    "gate",
    "base_sha",
    "head_sha",
    "scope_hash",
    "repository",
    "branch",
    "lease_id",
    "actor_id",
)

_ALLOWED_GATES = frozenset(
    {
        "G0_CONTEXT",
        "G1_ALIGNMENT",
        "G2_EXECUTION",
        "G3_PR",
        "G4_MERGE",
        "G5_DEPLOY",
        "G6_PRODUCTION_DATA",
    }
)


class LeaseAcquisitionError(RuntimeError):
    """Raised when acquisition is rejected (fail-closed binding / identity)."""


def _validate_binding(
    *,
    task_id: str,
    run_id: str,
    node_id: str,
    gate: str,
    base_sha: str,
    head_sha: str,
    scope_hash: str,
    repository: str,
    branch: str,
    lease_id: str,
    actor_id: str,
) -> None:
    provided = {
        "task_id": task_id,
        "run_id": run_id,
        "node_id": node_id,
        "gate": gate,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "scope_hash": scope_hash,
        "repository": repository,
        "branch": branch,
        "lease_id": lease_id,
        "actor_id": actor_id,
    }
    missing = [name for name, value in provided.items() if not str(value).strip()]
    if missing:
        raise LeaseAcquisitionError(
            "acquisition rejected: missing required binding fields: " + ", ".join(missing)
        )
    if gate not in _ALLOWED_GATES:
        raise LeaseAcquisitionError(f"acquisition rejected: ambiguous gate identity: {gate!r}")
    if len(base_sha) != 40 or not all(ch in "0123456789abcdef" for ch in base_sha):
        raise LeaseAcquisitionError("acquisition rejected: base_sha must be a 40-char lowercase hex SHA")
    if len(head_sha) != 40 or not all(ch in "0123456789abcdef" for ch in head_sha):
        raise LeaseAcquisitionError("acquisition rejected: head_sha must be a 40-char lowercase hex SHA")
    if not scope_hash.startswith("sha256:"):
        raise LeaseAcquisitionError("acquisition rejected: scope_hash must be a sha256: digest")


def _next_fencing_token(observed_fencing_token: int | None) -> int:
    if observed_fencing_token is None:
        return 1
    return observed_fencing_token + 1


def decide_lease_acquisition(
    *,
    task_id: str,
    run_id: str,
    node_id: str,
    gate: str,
    base_sha: str,
    head_sha: str,
    scope_hash: str,
    repository: str,
    branch: str,
    lease_id: str,
    actor_id: str,
    actor_fencing_token: int | None = None,
    observed_lease_holder: str | None = None,
    observed_fencing_token: int | None = None,
    observed_scope_hash: str | None = None,
    observed_repository: str | None = None,
    observed_run_id: str | None = None,
    lease_expired: bool = False,
    side_effect_status: str = "NONE",
    readback_status: str = "VERIFIED_ZERO_EFFECT",
    duplicate_agent_detected: bool = False,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Evaluate whether the actor may acquire the requested lease.

    Returns a deterministic decision dictionary. When acquisition is allowed,
    the decision includes a monotonic ``fencing_token``.
    """
    _validate_binding(
        task_id=task_id,
        run_id=run_id,
        node_id=node_id,
        gate=gate,
        base_sha=base_sha,
        head_sha=head_sha,
        scope_hash=scope_hash,
        repository=repository,
        branch=branch,
        lease_id=lease_id,
        actor_id=actor_id,
    )

    if observed_scope_hash is not None and observed_scope_hash != scope_hash:
        outcome, reason = "SCOPE_MISMATCH", "OBSERVED_SCOPE_HASH_MISMATCH"
        advancement_allowed = False
        side_effect_allowed = False
        reacquire_required = False
        fencing_token = None
    elif observed_repository is not None and observed_repository != repository:
        outcome, reason = "SCOPE_MISMATCH", "OBSERVED_REPOSITORY_MISMATCH"
        advancement_allowed = False
        side_effect_allowed = False
        reacquire_required = False
        fencing_token = None
    elif observed_run_id is not None and observed_run_id != run_id:
        outcome, reason = "SCOPE_MISMATCH", "RUN_ID_MISMATCH"
        advancement_allowed = False
        side_effect_allowed = False
        reacquire_required = False
        fencing_token = None
    elif observed_lease_holder is None:
        outcome, reason = "ACQUIRED", "NO_COMPETING_ACTIVE_LEASE"
        advancement_allowed = True
        side_effect_allowed = side_effect_status == "NONE"
        reacquire_required = False
        fencing_token = _next_fencing_token(observed_fencing_token)
    elif observed_lease_holder == actor_id:
        if not lease_expired:
            outcome, reason = "ACQUIRED", "CURRENT_HOLDER_LEASE_STILL_VALID"
            advancement_allowed = True
            side_effect_allowed = side_effect_status == "NONE"
            reacquire_required = False
            fencing_token = _next_fencing_token(observed_fencing_token)
        elif side_effect_status in {"COMMITTED", "UNKNOWN", "PENDING"}:
            outcome, reason = "RECONCILE", "EXPIRED_LEASE_HAS_SIDE_EFFECTS"
            advancement_allowed = False
            side_effect_allowed = False
            reacquire_required = False
            fencing_token = None
        elif readback_status != "VERIFIED_ZERO_EFFECT":
            outcome, reason = "REACQUIRE_REQUIRED", "SAFE_READBACK_REQUIRED_AFTER_EXPIRY"
            advancement_allowed = False
            side_effect_allowed = False
            reacquire_required = True
            fencing_token = None
        else:
            outcome, reason = "ACQUIRED", "LEASE_REACQUIRED_WITH_MONOTONIC_FENCE"
            advancement_allowed = True
            side_effect_allowed = True
            reacquire_required = False
            fencing_token = _next_fencing_token(observed_fencing_token)
    else:
        if (
            actor_fencing_token is not None
            and observed_fencing_token is not None
            and actor_fencing_token < observed_fencing_token
        ):
            outcome, reason = "FENCE_STALE_WORKER", "WORKER_FENCING_TOKEN_STALE"
        elif duplicate_agent_detected:
            outcome, reason = "FENCE_DUPLICATE_AGENT", "DUPLICATE_AGENT_RACE_DETECTED"
        else:
            outcome, reason = "FENCE_DUPLICATE_AGENT", "COMPETING_ACTIVE_LEASE"
        advancement_allowed = False
        side_effect_allowed = False
        reacquire_required = False
        fencing_token = None

    decision = {
        "schema_version": "1.0",
        "artifact_type": "lease-acquisition-decision",
        "task_id": task_id,
        "run_id": run_id,
        "node_id": node_id,
        "gate": gate,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "scope_hash": scope_hash,
        "repository": repository,
        "branch": branch,
        "lease_id": lease_id,
        "actor_id": actor_id,
        "actor_fencing_token": actor_fencing_token,
        "observed_lease_holder": observed_lease_holder,
        "observed_fencing_token": observed_fencing_token,
        "observed_scope_hash": observed_scope_hash,
        "observed_repository": observed_repository,
        "lease_expired": lease_expired,
        "side_effect_status": side_effect_status,
        "readback_status": readback_status,
        "duplicate_agent_detected": duplicate_agent_detected,
        "observed_at": observed_at or _now(),
        "outcome": outcome,
        "reason_code": reason,
        "advancement_allowed": advancement_allowed,
        "side_effect_allowed": side_effect_allowed,
        "reacquire_required": reacquire_required,
        "fencing_token": fencing_token,
        "fencing_enforced": True,
    }
    decision["decision_digest"] = digest_payload(
        {k: v for k, v in decision.items() if k != "decision_digest"}
    )
    return decision


def is_replay_equivalent(first: dict[str, Any], second: dict[str, Any]) -> bool:
    def stable(payload: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in payload.items() if k not in {"observed_at", "decision_digest"}}

    return digest_payload(stable(first)) == digest_payload(stable(second))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Route lease acquisition from evidence JSON.")
    parser.add_argument("--payload", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(decide_lease_acquisition(**json.loads(args.payload)), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
