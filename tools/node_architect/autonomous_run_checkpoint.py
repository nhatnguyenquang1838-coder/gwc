#!/usr/bin/env python3
"""Deterministic autonomous run checkpoint for the pre-prod runtime MVP (SCRUM-276).

This module wraps the existing replay-safe checkpoint primitives for the
autonomous pre-prod runner. It derives a deterministic run key from the approved
run manifest so the same manifest replay yields an identical checkpoint digest
and never creates a duplicate branch/commit/PR/comment/merge effect on its own.

The module is local and data-oriented. It does not call GitHub, Jira, Slack, or
production services. Callers supply already-authorized task/repository/scope
data; the capturer fails closed when binding identity is missing or ambiguous.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .checkpoint_store import canonical_json, digest_payload


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


class AutonomousRunCheckpointError(RuntimeError):
    """Raised when an autonomous run checkpoint is rejected (fail-closed)."""


def manifest_digest(manifest: Mapping[str, Any]) -> str:
    """Deterministic digest over the approved run manifest (order-independent)."""
    return digest_payload(manifest)


def run_key(task_id: str, run_id: str, manifest_digest_value: str) -> str:
    """Stable checkpoint key for an autonomous run.

    Same (task_id, run_id, manifest_digest) always yields the same key, so a
    replay of the same approved manifest cannot spawn a second run identity.
    """
    return f"{task_id}:{run_id}:{manifest_digest_value}"


def _validate_binding(
    *,
    task_id: str,
    repository: str,
    base_sha: str,
    head_sha: str,
    scope_hash: str,
    manifest_digest_value: str,
) -> None:
    provided = {
        "task_id": task_id,
        "repository": repository,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "scope_hash": scope_hash,
        "manifest_digest": manifest_digest_value,
    }
    missing = [name for name, value in provided.items() if not str(value).strip()]
    if missing:
        raise AutonomousRunCheckpointError(
            "autonomous run checkpoint rejected: missing binding fields: "
            + ", ".join(missing)
        )
    if len(base_sha) != 40 or not all(ch in "0123456789abcdef" for ch in base_sha):
        raise AutonomousRunCheckpointError("base_sha must be a 40-char lowercase hex SHA")
    if len(head_sha) != 40 or not all(ch in "0123456789abcdef" for ch in head_sha):
        raise AutonomousRunCheckpointError("head_sha must be a 40-char lowercase hex SHA")
    if not scope_hash.startswith("sha256:"):
        raise AutonomousRunCheckpointError("scope_hash must be a sha256: digest")


@dataclass(frozen=True)
class AutonomousRunCheckpoint:
    task_id: str
    run_id: str
    repository: str
    base_sha: str
    head_sha: str
    scope_hash: str
    manifest_digest_value: str
    checkpoint_key: str
    state_digest: str
    completed_node_ids: tuple[str, ...]
    next_node_id: str | None
    captured_at: str


def capture_autonomous_run(
    *,
    task_id: str,
    run_id: str,
    repository: str,
    base_sha: str,
    head_sha: str,
    scope_hash: str,
    manifest: Mapping[str, Any],
    completed_node_ids: Sequence[str] = (),
    next_node_id: str | None = None,
    timestamp: str | None = None,
) -> AutonomousRunCheckpoint:
    """Capture a deterministic autonomous run checkpoint.

    Fails closed when task/repository/scope identity is missing or ambiguous.
    Produces the same ``state_digest`` for an identical manifest + progress.
    """
    _validate_binding(
        task_id=task_id,
        repository=repository,
        base_sha=base_sha,
        head_sha=head_sha,
        scope_hash=scope_hash,
        manifest_digest_value=manifest_digest(manifest),
    )
    if not isinstance(manifest, Mapping) or not manifest:
        raise AutonomousRunCheckpointError("manifest must be a non-empty mapping")
    normalized_completed = tuple(str(node) for node in (completed_node_ids or ()))
    state = {
        "manifest_digest": manifest_digest(manifest),
        "completed_node_ids": normalized_completed,
        "next_node_id": next_node_id,
    }
    state_digest = digest_payload(state)
    captured_at = timestamp or _now()
    return AutonomousRunCheckpoint(
        task_id=task_id,
        run_id=run_id,
        repository=repository,
        base_sha=base_sha,
        head_sha=head_sha,
        scope_hash=scope_hash,
        manifest_digest_value=manifest_digest(manifest),
        checkpoint_key=run_key(task_id, run_id, manifest_digest(manifest)),
        state_digest=state_digest,
        completed_node_ids=normalized_completed,
        next_node_id=next_node_id,
        captured_at=captured_at,
    )


def is_replay_equivalent(first: AutonomousRunCheckpoint, second: AutonomousRunCheckpoint) -> bool:
    """Two checkpoints are replay-equivalent when their deterministic identity matches."""
    if not isinstance(first, AutonomousRunCheckpoint) or not isinstance(second, AutonomousRunCheckpoint):
        return False
    return (
        first.checkpoint_key == second.checkpoint_key
        and first.state_digest == second.state_digest
    )


__all__ = [
    "AutonomousRunCheckpoint",
    "AutonomousRunCheckpointError",
    "capture_autonomous_run",
    "is_replay_equivalent",
    "manifest_digest",
    "run_key",
]
