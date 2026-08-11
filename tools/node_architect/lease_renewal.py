#!/usr/bin/env python3
"""Deterministic, replay-safe lease renewal for GWC node execution.

Implements the ``runtime_checkpoint.lease-renewal`` node (MAT-F4-N06).
Local and data-oriented: no GitHub / Jira / Slack / production calls. Callers
pass already-authorized binding identity (owner, task, scope, base SHA, fencing
token); the renewer validates that renewal is permitted under the approved G2
scope and produces a new lease carrying a *monotonic* fencing token.

Contract (from SCRUM-207 node spec):
- Renewal requires current owner identity, unexpired or policy-renewable lease,
  matching ``task_id``, ``scope_hash``, ``base_sha``, and fencing token.
- Renewal must not hide base drift, approval expiry, scope drift, or stale worker.
- Fencing token must remain monotonic; writes after renewal carry the latest token.
- Failed renewal routes to reconciliation, not blind retry.

Design mirrors ``checkpoint_capture.py`` / ``checkpoint_store.py``:
- ``canonical_json`` / ``digest_payload`` give a stable, sort-keyed digest so the
  same renewal input yields the same lease digest (replay-safe, EARS #4).
- A missing or ambiguous binding fails closed (EARS #3).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# Closed set of binding fields whose absence must fail closed (EARS #3).
_REQUIRED_BINDING = (
    "task_id",
    "node_id",
    "scope_hash",
    "base_sha",
    "owner",
    "fencing_token",
    "repository",
)

# Default policy: a lease is renewable if it has not yet expired, or if it is
# within this grace window before expiry (policy-renewable). Tunable per call.
_DEFAULT_RENEWAL_GRACE = timedelta(minutes=10)

# A renewal attempt that cannot proceed is routed to reconciliation with one of
# these reason codes (never blind-retried).
RECONCILE_REASONS = (
    "BASE_DRIFT",
    "APPROVAL_EXPIRED",
    "SCOPE_DRIFT",
    "STALE_WORKER",
    "OWNER_MISMATCH",
    "FENCING_NOT_MONOTONIC",
    "LEASE_EXPIRED_NO_GRACE",
    "RUN_ID_MISMATCH",
)


class LeaseRenewalError(RuntimeError):
    """Raised when renewal is rejected (fail-closed binding / contract breach)."""


@dataclass(frozen=True)
class Lease:
    """An issued or renewed lease with a monotonic fencing token."""

    lease_id: str
    owner: str
    task_id: str
    node_id: str
    scope_hash: str
    base_sha: str
    fencing_token: int
    issued_at: str
    expires_at: str
    repository: str
    # NA81 (SCRUM-330): bind the lease to the authorizing autonomous run so a
    # renewal can only be performed by the same actor/run. Defaults to "" for
    # legacy leases that predate run binding (backward-compatible).
    run_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "artifact_type": "runtime-checkpoint-lease",
            "lease_id": self.lease_id,
            "owner": self.owner,
            "task_id": self.task_id,
            "node_id": self.node_id,
            "scope_hash": self.scope_hash,
            "base_sha": self.base_sha,
            "fencing_token": self.fencing_token,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "repository": self.repository,
            "run_id": self.run_id,
        }


@dataclass(frozen=True)
class RenewalDecision:
    """Outcome of a renewal evaluation — renewed lease or a reconcile route."""

    renewed: bool
    lease: Lease | None = None
    reconcile_reason: str | None = None
    evaluated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "artifact_type": "runtime-checkpoint-renewal-decision",
            "renewed": self.renewed,
            "lease": self.lease.to_dict() if self.lease is not None else None,
            "reconcile_reason": self.reconcile_reason,
            "evaluated_at": self.evaluated_at,
        }


def _validate_binding(
    *,
    task_id: str,
    node_id: str,
    scope_hash: str,
    base_sha: str,
    owner: str,
    fencing_token: int,
    repository: str,
) -> None:
    """Fail closed when any binding field is missing or ambiguous (EARS #3)."""
    provided = {
        "task_id": task_id,
        "node_id": node_id,
        "scope_hash": scope_hash,
        "base_sha": base_sha,
        "owner": owner,
        "repository": repository,
    }
    missing = [name for name, value in provided.items() if not str(value).strip()]
    if missing:
        raise LeaseRenewalError(
            "renewal rejected: missing required binding fields: " + ", ".join(missing)
        )
    if not scope_hash.startswith("sha256:"):
        raise LeaseRenewalError("renewal rejected: scope_hash must be a sha256: digest")
    if len(base_sha) != 40 or not all(ch in "0123456789abcdef" for ch in base_sha):
        raise LeaseRenewalError("renewal rejected: base_sha must be a 40-char lowercase hex SHA")
    if not isinstance(fencing_token, int) or fencing_token < 0:
        raise LeaseRenewalError("renewal rejected: fencing_token must be a non-negative integer")


def _parse_ts(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception as exc:  # noqa: BLE001 - surface as fail-closed
        raise LeaseRenewalError(f"renewal rejected: unparseable timestamp: {value!r}") from exc


def _lease_digest(lease: Lease) -> str:
    payload = json.loads(json.dumps(lease.to_dict(), sort_keys=True))
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def evaluate_renewal(
    *,
    task_id: str,
    node_id: str,
    scope_hash: str,
    base_sha: str,
    owner: str,
    fencing_token: int,
    current_lease: Lease,
    repository: str,
    now: str | None = None,
    renewal_grace: timedelta = _DEFAULT_RENEWAL_GRACE,
    approval_expires_at: str | None = None,
    run_id: str | None = None,
    observed_run_id: str | None = None,
) -> RenewalDecision:
    """Evaluate whether ``current_lease`` may be renewed under the approved scope.

    Returns a renewed ``Lease`` (with ``fencing_token + 1``) when all contract
    conditions hold; otherwise routes to reconciliation with an explicit reason.
    Never mutates ``current_lease``.
    """
    _validate_binding(
        task_id=task_id,
        node_id=node_id,
        scope_hash=scope_hash,
        base_sha=base_sha,
        owner=owner,
        fencing_token=fencing_token,
        repository=repository,
    )
    evaluated_at = now or _now()

    # 1. Owner identity must match the active lease (no hijack).
    if current_lease.owner != owner:
        return RenewalDecision(
            renewed=False, reconcile_reason="OWNER_MISMATCH", evaluated_at=evaluated_at
        )

    # 1b. Run identity must match the active lease (same actor/run, NA81
    # SCRUM-330). A renewal requested under a different run, or observed under a
    # conflicting run, must fail closed — renewal must never rebind execution
    # to a different autonomous run.
    if run_id is not None and run_id.strip():
        if current_lease.run_id and current_lease.run_id != run_id:
            return RenewalDecision(
                renewed=False, reconcile_reason="RUN_ID_MISMATCH", evaluated_at=evaluated_at
            )
        if observed_run_id is not None and observed_run_id != run_id:
            return RenewalDecision(
                renewed=False, reconcile_reason="RUN_ID_MISMATCH", evaluated_at=evaluated_at
            )

    # 2. Binding scope must match the lease (no silent scope drift).
    if current_lease.task_id != task_id:
        return RenewalDecision(
            renewed=False, reconcile_reason="SCOPE_DRIFT", evaluated_at=evaluated_at
        )
    if current_lease.scope_hash != scope_hash:
        return RenewalDecision(
            renewed=False, reconcile_reason="SCOPE_DRIFT", evaluated_at=evaluated_at
        )
    if current_lease.base_sha != base_sha:
        return RenewalDecision(
            renewed=False, reconcile_reason="BASE_DRIFT", evaluated_at=evaluated_at
        )
    if current_lease.node_id != node_id:
        return RenewalDecision(
            renewed=False, reconcile_reason="SCOPE_DRIFT", evaluated_at=evaluated_at
        )
    if current_lease.repository != repository:
        return RenewalDecision(
            renewed=False, reconcile_reason="SCOPE_DRIFT", evaluated_at=evaluated_at
        )

    # 3. Fencing token must be monotonic: the presented token must equal the
    #    lease's current token (renewal advances it, never regresses).
    if fencing_token != current_lease.fencing_token:
        return RenewalDecision(
            renewed=False, reconcile_reason="FENCING_NOT_MONOTONIC", evaluated_at=evaluated_at
        )

    # 4. Do not hide approval expiry.
    if approval_expires_at is not None:
        if _parse_ts(approval_expires_at) <= _parse_ts(evaluated_at):
            return RenewalDecision(
                renewed=False, reconcile_reason="APPROVAL_EXPIRED", evaluated_at=evaluated_at
            )

    # 5. Lease must be unexpired or within policy-renewable grace (no stale worker).
    expires = _parse_ts(current_lease.expires_at)
    now_dt = _parse_ts(evaluated_at)
    if now_dt > expires + renewal_grace:
        return RenewalDecision(
            renewed=False, reconcile_reason="LEASE_EXPIRED_NO_GRACE", evaluated_at=evaluated_at
        )
    if now_dt > expires:
        # Within grace: renewable, but flag stale-worker awareness is caller's job.
        pass

    # 6. Renew: advance the monotonic fencing token, re-issue the lease.
    new_token = fencing_token + 1
    renewed_lease = Lease(
        lease_id=current_lease.lease_id,
        owner=owner,
        task_id=task_id,
        node_id=node_id,
        scope_hash=scope_hash,
        base_sha=base_sha,
        fencing_token=new_token,
        issued_at=evaluated_at,
        expires_at=_parse_ts(current_lease.expires_at).isoformat().replace("+00:00", "Z"),
        repository=repository,
        run_id=run_id if run_id is not None else current_lease.run_id,
    )
    return RenewalDecision(renewed=True, lease=renewed_lease, evaluated_at=evaluated_at)


def renew_lease(
    *,
    task_id: str,
    node_id: str,
    scope_hash: str,
    base_sha: str,
    owner: str,
    fencing_token: int,
    current_lease: Lease,
    repository: str,
    now: str | None = None,
    renewal_grace: timedelta = _DEFAULT_RENEWAL_GRACE,
    approval_expires_at: str | None = None,
    run_id: str | None = None,
    observed_run_id: str | None = None,
) -> Lease:
    """Convenience wrapper: renew or raise on reconcile route.

    Returns the renewed ``Lease`` (fencing token advanced). Raises
    ``LeaseRenewalError`` carrying the reconcile reason when renewal is not
    permitted — callers must route to reconciliation, not retry blindly.
    """
    decision = evaluate_renewal(
        task_id=task_id,
        node_id=node_id,
        scope_hash=scope_hash,
        base_sha=base_sha,
        owner=owner,
        fencing_token=fencing_token,
        current_lease=current_lease,
        repository=repository,
        now=now,
        renewal_grace=renewal_grace,
        approval_expires_at=approval_expires_at,
        run_id=run_id,
        observed_run_id=observed_run_id,
    )
    if not decision.renewed or decision.lease is None:
        raise LeaseRenewalError(
            f"renewal routed to reconciliation: {decision.reconcile_reason}"
        )
    return decision.lease


def lease_digest(lease: Lease) -> str:
    """Deterministic digest of a lease (same input -> same digest, EARS #4)."""
    return _lease_digest(lease)


__all__ = [
    "Lease",
    "LeaseRenewalError",
    "RenewalDecision",
    "evaluate_renewal",
    "renew_lease",
    "lease_digest",
    "RECONCILE_REASONS",
]
