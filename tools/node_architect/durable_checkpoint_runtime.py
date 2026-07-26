#!/usr/bin/env python3
"""Durable checkpoint/CAS/lease/resume pilot for SCRUM-109.

Provider-neutral and in-memory by design. It models the correctness boundary
from SCRUM-105/SCRUM-106 without adding a scheduler, database adapter,
deployment, migration, credential handling, or production runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Mapping, Sequence


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class RuntimeBinding:
    """Stable identity fields that a resume must preserve."""

    task_id: str
    repository: str
    base_sha: str
    scope_hash: str
    graph_revision: str
    runtime_version: str = "durable-checkpoint-runtime@0.1"
    node_version: str = "durable-checkpoint-cas-lease-resume@0.1"

    def validate(self) -> None:
        required = {
            "task_id": self.task_id,
            "repository": self.repository,
            "base_sha": self.base_sha,
            "scope_hash": self.scope_hash,
            "graph_revision": self.graph_revision,
            "runtime_version": self.runtime_version,
            "node_version": self.node_version,
        }
        missing = [name for name, value in required.items() if not str(value).strip()]
        if missing:
            raise ValueError("missing binding fields: " + ", ".join(missing))
        if len(self.base_sha) != 40 or not all(ch in "0123456789abcdef" for ch in self.base_sha):
            raise ValueError("base_sha must be a 40-character lowercase hex SHA")


@dataclass(frozen=True)
class Checkpoint:
    """Canonical resumable state for a run."""

    run_id: str
    binding: RuntimeBinding
    current_node_id: str
    next_node_id: str
    next_action: str
    gate: str
    status: str
    revision: int
    lease_owner: str | None
    lease_expires_at_utc: datetime | None
    fencing_token: int
    pending_actions: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()

    def validate(self) -> None:
        self.binding.validate()
        required = {
            "run_id": self.run_id,
            "current_node_id": self.current_node_id,
            "next_node_id": self.next_node_id,
            "next_action": self.next_action,
            "gate": self.gate,
            "status": self.status,
        }
        missing = [name for name, value in required.items() if not str(value).strip()]
        if missing:
            raise ValueError("missing checkpoint fields: " + ", ".join(missing))
        if self.revision < 0:
            raise ValueError("revision must be non-negative")
        if self.fencing_token < 0:
            raise ValueError("fencing_token must be non-negative")
        if self.lease_expires_at_utc is not None:
            _ensure_aware_utc(self.lease_expires_at_utc)


class CheckpointError(RuntimeError):
    """Base class for checkpoint runtime failures."""


class RunAlreadyExists(CheckpointError):
    """Raised when creating a duplicate run."""


class RunNotFound(CheckpointError):
    """Raised when a run cannot be found."""


class CheckpointCasMismatch(CheckpointError):
    """Raised when expected revision does not match stored revision."""


class LeaseConflict(CheckpointError):
    """Raised when a non-expired lease prevents ownership."""


class LeaseRequired(CheckpointError):
    """Raised when a mutation lacks an active matching lease."""


class FencingTokenMismatch(CheckpointError):
    """Raised when a stale worker tries to advance state."""


class StaleCheckpoint(CheckpointError):
    """Raised when resume binding differs from durable state."""


class DurableCheckpointStore:
    """In-memory provider-neutral durable checkpoint boundary."""

    def __init__(self) -> None:
        self._checkpoints: dict[str, Checkpoint] = {}

    def create_run(
        self,
        *,
        run_id: str,
        binding: RuntimeBinding,
        current_node_id: str,
        next_node_id: str,
        next_action: str,
        gate: str,
        status: str = "READY",
        evidence: Sequence[str] = (),
    ) -> Checkpoint:
        if run_id in self._checkpoints:
            raise RunAlreadyExists(run_id)
        checkpoint = Checkpoint(
            run_id=run_id,
            binding=binding,
            current_node_id=current_node_id,
            next_node_id=next_node_id,
            next_action=next_action,
            gate=gate,
            status=status,
            revision=0,
            lease_owner=None,
            lease_expires_at_utc=None,
            fencing_token=0,
            evidence=tuple(evidence),
        )
        checkpoint.validate()
        self._checkpoints[run_id] = checkpoint
        return checkpoint

    def read_checkpoint(self, run_id: str) -> Checkpoint:
        try:
            return self._checkpoints[run_id]
        except KeyError as exc:
            raise RunNotFound(run_id) from exc

    def acquire_lease(
        self,
        *,
        run_id: str,
        lease_owner: str,
        ttl_seconds: int,
        now: datetime | None = None,
    ) -> Checkpoint:
        if not lease_owner.strip():
            raise ValueError("lease_owner is required")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        current = self.read_checkpoint(run_id)
        observed_at = _ensure_aware_utc(now or _utc_now())
        if self._lease_active(current, observed_at) and current.lease_owner != lease_owner:
            raise LeaseConflict(f"active lease belongs to {current.lease_owner}")
        next_checkpoint = replace(
            current,
            lease_owner=lease_owner,
            lease_expires_at_utc=observed_at + timedelta(seconds=ttl_seconds),
            fencing_token=current.fencing_token + 1,
            status="LEASED",
        )
        next_checkpoint.validate()
        self._checkpoints[run_id] = next_checkpoint
        return next_checkpoint

    def renew_lease(
        self,
        *,
        run_id: str,
        lease_owner: str,
        fencing_token: int,
        ttl_seconds: int,
        now: datetime | None = None,
    ) -> Checkpoint:
        current = self.read_checkpoint(run_id)
        observed_at = _ensure_aware_utc(now or _utc_now())
        self._require_current_lease(current, lease_owner, fencing_token, observed_at)
        next_checkpoint = replace(current, lease_expires_at_utc=observed_at + timedelta(seconds=ttl_seconds))
        next_checkpoint.validate()
        self._checkpoints[run_id] = next_checkpoint
        return next_checkpoint

    def cas_checkpoint(
        self,
        *,
        run_id: str,
        expected_revision: int,
        lease_owner: str,
        fencing_token: int,
        next_state: Mapping[str, object],
        now: datetime | None = None,
    ) -> Checkpoint:
        current = self.read_checkpoint(run_id)
        observed_at = _ensure_aware_utc(now or _utc_now())
        self._require_current_lease(current, lease_owner, fencing_token, observed_at)
        if expected_revision != current.revision:
            raise CheckpointCasMismatch(
                f"expected revision {expected_revision}, current revision {current.revision}"
            )
        allowed = {"current_node_id", "next_node_id", "next_action", "gate", "status", "pending_actions", "evidence"}
        unexpected = set(next_state) - allowed
        if unexpected:
            raise ValueError("unsupported checkpoint update fields: " + ", ".join(sorted(unexpected)))
        updated = replace(
            current,
            current_node_id=str(next_state.get("current_node_id", current.current_node_id)),
            next_node_id=str(next_state.get("next_node_id", current.next_node_id)),
            next_action=str(next_state.get("next_action", current.next_action)),
            gate=str(next_state.get("gate", current.gate)),
            status=str(next_state.get("status", current.status)),
            pending_actions=tuple(str(item) for item in next_state.get("pending_actions", current.pending_actions)),
            evidence=tuple(str(item) for item in next_state.get("evidence", current.evidence)),
            revision=current.revision + 1,
        )
        if updated.binding != current.binding:
            raise StaleCheckpoint("binding mutation is forbidden")
        updated.validate()
        self._checkpoints[run_id] = updated
        return updated

    def resume_checkpoint(
        self,
        *,
        run_id: str,
        expected_binding: RuntimeBinding,
        lease_owner: str,
        ttl_seconds: int,
        now: datetime | None = None,
    ) -> Checkpoint:
        current = self.read_checkpoint(run_id)
        if current.binding != expected_binding:
            raise StaleCheckpoint("resume binding does not match checkpoint binding")
        observed_at = _ensure_aware_utc(now or _utc_now())
        if current.lease_owner == lease_owner and self._lease_active(current, observed_at):
            return self.renew_lease(
                run_id=run_id,
                lease_owner=lease_owner,
                fencing_token=current.fencing_token,
                ttl_seconds=ttl_seconds,
                now=observed_at,
            )
        if self._lease_active(current, observed_at):
            raise LeaseConflict(f"active lease belongs to {current.lease_owner}")
        return self.acquire_lease(run_id=run_id, lease_owner=lease_owner, ttl_seconds=ttl_seconds, now=observed_at)

    def release_lease(
        self,
        *,
        run_id: str,
        lease_owner: str,
        fencing_token: int,
        now: datetime | None = None,
    ) -> Checkpoint:
        current = self.read_checkpoint(run_id)
        observed_at = _ensure_aware_utc(now or _utc_now())
        self._require_current_lease(current, lease_owner, fencing_token, observed_at)
        next_checkpoint = replace(current, lease_owner=None, lease_expires_at_utc=None, status="LEASE_RELEASED")
        next_checkpoint.validate()
        self._checkpoints[run_id] = next_checkpoint
        return next_checkpoint

    @staticmethod
    def _lease_active(checkpoint: Checkpoint, observed_at: datetime) -> bool:
        if checkpoint.lease_owner is None or checkpoint.lease_expires_at_utc is None:
            return False
        return _ensure_aware_utc(checkpoint.lease_expires_at_utc) > observed_at

    def _require_current_lease(
        self,
        checkpoint: Checkpoint,
        lease_owner: str,
        fencing_token: int,
        observed_at: datetime,
    ) -> None:
        if not self._lease_active(checkpoint, observed_at):
            raise LeaseRequired("active lease is required")
        if checkpoint.lease_owner != lease_owner:
            raise LeaseRequired(f"lease owner mismatch: {checkpoint.lease_owner} != {lease_owner}")
        if checkpoint.fencing_token != fencing_token:
            raise FencingTokenMismatch(f"fencing token mismatch: {fencing_token} != {checkpoint.fencing_token}")


__all__ = [
    "Checkpoint",
    "CheckpointCasMismatch",
    "CheckpointError",
    "DurableCheckpointStore",
    "FencingTokenMismatch",
    "LeaseConflict",
    "LeaseRequired",
    "RunAlreadyExists",
    "RunNotFound",
    "RuntimeBinding",
    "StaleCheckpoint",
]
