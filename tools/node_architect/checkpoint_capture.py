#!/usr/bin/env python3
"""Deterministic replay-safe checkpoint capture for GWC node execution.

Implements the ``runtime_checkpoint.checkpoint-capture`` node (MAT-F4-N01).
This module is local and data-oriented. It does not call GitHub, Jira, Slack,
or production services. Callers pass already-authorized task, repository, gate,
and scope data; the capturer normalizes the snapshot shape so the same input
produces the same digest, fails closed when binding identity is missing or
ambiguous, and supports replay-read reconstruction of the exact next action.

Design (shared with ``checkpoint_store.py``):
- ``canonical_json`` / ``digest_payload`` produce a stable, sort-keyed digest.
- The captured ``state_digest`` is derived from the same canonical form so an
  identical capture yields an identical digest (EARS #4).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .checkpoint_store import canonical_json, digest_payload


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# Closed set of binding fields whose absence must fail closed (EARS #3).
_REQUIRED_BINDING = (
    "task_id",
    "run_id",
    "node_id",
    "gate",
    "base_sha",
    "head_sha",
    "scope_hash",
    "graph_revision",
    "repository",
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


class CheckpointCaptureError(RuntimeError):
    """Raised when capture is rejected (fail-closed binding / identity)."""


@dataclass(frozen=True)
class PendingAction:
    """An exact, replayable pending action captured before suspension."""

    action_id: str
    target: str
    authority_gate: str
    idempotency_key: str

    def to_dict(self) -> dict[str, str]:
        return {
            "action_id": self.action_id,
            "target": self.target,
            "authority_gate": self.authority_gate,
            "idempotency_key": self.idempotency_key,
        }


@dataclass(frozen=True)
class CheckpointCapture:
    """Deterministic, replay-safe snapshot of bounded execution state."""

    task_id: str
    run_id: str
    node_id: str
    gate: str
    base_sha: str
    head_sha: str
    scope_hash: str
    graph_revision: str
    repository: str
    state_digest: str
    pending_actions: tuple[PendingAction, ...] = ()
    next_action: str | None = None
    captured_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "artifact_type": "runtime-checkpoint-capture",
            "task_id": self.task_id,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "gate": self.gate,
            "base_sha": self.base_sha,
            "head_sha": self.head_sha,
            "scope_hash": self.scope_hash,
            "graph_revision": self.graph_revision,
            "repository": self.repository,
            "state_digest": self.state_digest,
            "pending_actions": [a.to_dict() for a in self.pending_actions],
            "next_action": self.next_action,
            "captured_at": self.captured_at,
        }


def _validate_binding(*, task_id: str, run_id: str, node_id: str, gate: str,
                       base_sha: str, head_sha: str, scope_hash: str,
                       graph_revision: str, repository: str) -> None:
    """Fail closed when any binding field is missing or ambiguous (EARS #3)."""
    provided = {
        "task_id": task_id,
        "run_id": run_id,
        "node_id": node_id,
        "gate": gate,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "scope_hash": scope_hash,
        "graph_revision": graph_revision,
        "repository": repository,
    }
    missing = [name for name, value in provided.items() if not str(value).strip()]
    if missing:
        raise CheckpointCaptureError(
            "capture rejected: missing required binding fields: " + ", ".join(missing)
        )
    # Ambiguity check: gate must be a single known gate identity.
    if gate not in _ALLOWED_GATES:
        raise CheckpointCaptureError(f"capture rejected: ambiguous gate identity: {gate!r}")
    if len(base_sha) != 40 or not all(ch in "0123456789abcdef" for ch in base_sha):
        raise CheckpointCaptureError("capture rejected: base_sha must be a 40-char lowercase hex SHA")
    if len(head_sha) != 40 or not all(ch in "0123456789abcdef" for ch in head_sha):
        raise CheckpointCaptureError("capture rejected: head_sha must be a 40-char lowercase hex SHA")
    if not scope_hash.startswith("sha256:"):
        raise CheckpointCaptureError("capture rejected: scope_hash must be a sha256: digest")


def _digest_state(state: Mapping[str, Any]) -> str:
    """Canonical digest of the supplied execution state (deterministic)."""
    return digest_payload(state)


def capture_checkpoint(
    *,
    task_id: str,
    run_id: str,
    node_id: str,
    gate: str,
    base_sha: str,
    head_sha: str,
    scope_hash: str,
    graph_revision: str,
    repository: str,
    state: Mapping[str, Any],
    pending_actions: Sequence[PendingAction] = (),
    next_action: str | None = None,
    timestamp: str | None = None,
) -> CheckpointCapture:
    """Capture a deterministic, replay-safe checkpoint snapshot.

    Fails closed (``CheckpointCaptureError``) when task/repository/scope/gate
    identity is missing or ambiguous (EARS #3). Produces the same
    ``state_digest`` for identical input (EARS #4).

    Capture is intended before writes, before suspend, and before handoff to
    persistence. This function does not itself persist; pass the returned
    ``CheckpointCapture`` to ``checkpoint_store.persist_checkpoint``.
    """
    _validate_binding(
        task_id=task_id,
        run_id=run_id,
        node_id=node_id,
        gate=gate,
        base_sha=base_sha,
        head_sha=head_sha,
        scope_hash=scope_hash,
        graph_revision=graph_revision,
        repository=repository,
    )

    if state is None or not isinstance(state, Mapping):
        raise CheckpointCaptureError("capture rejected: state must be a mapping")

    normalized_pending = tuple(
        a if isinstance(a, PendingAction) else PendingAction(**dict(a))
        for a in (pending_actions or ())
    )
    # Validate each pending action carries exact identity (EARS #2).
    for action in normalized_pending:
        if not action.action_id.strip() or not action.target.strip() \
                or not action.authority_gate.strip() or not action.idempotency_key.strip():
            raise CheckpointCaptureError(
                "capture rejected: pending action requires exact action_id, target, "
                "authority_gate, and idempotency_key"
            )
        if action.authority_gate not in _ALLOWED_GATES:
            raise CheckpointCaptureError(
                f"capture rejected: pending action authority_gate ambiguous: {action.authority_gate!r}"
            )

    state_digest = _digest_state(state)
    captured_at = timestamp or _now()

    return CheckpointCapture(
        task_id=task_id,
        run_id=run_id,
        node_id=node_id,
        gate=gate,
        base_sha=base_sha,
        head_sha=head_sha,
        scope_hash=scope_hash,
        graph_revision=graph_revision,
        repository=repository,
        state_digest=state_digest,
        pending_actions=normalized_pending,
        next_action=next_action,
        captured_at=captured_at,
    )


def reconstruct_next_action(capture: CheckpointCapture) -> str | None:
    """Replay-read compatibility: reconstruct the exact next action.

    Returns ``capture.next_action`` when present and the surrounding binding is
    intact, enabling a resume to continue from the captured exact next action
    without allowing stale worker advancement.
    """
    if capture is None or not isinstance(capture, CheckpointCapture):
        raise CheckpointCaptureError("reconstruct requires a captured CheckpointCapture")
    # Binding integrity re-check on read-back (no stale advancement).
    _validate_binding(
        task_id=capture.task_id,
        run_id=capture.run_id,
        node_id=capture.node_id,
        gate=capture.gate,
        base_sha=capture.base_sha,
        head_sha=capture.head_sha,
        scope_hash=capture.scope_hash,
        graph_revision=capture.graph_revision,
        repository=capture.repository,
    )
    return capture.next_action


__all__ = [
    "CheckpointCapture",
    "CheckpointCaptureError",
    "PendingAction",
    "capture_checkpoint",
    "reconstruct_next_action",
]
