#!/usr/bin/env python3
"""Serial multi-task canary runner for the autonomous pre-prod runtime (SCRUM-276).

Given an approved run manifest of allowlisted tasks, the runner executes them
serially without human interaction between tasks. Each task runs only after the
previous one has produced a terminal, failure-closed reconciliation decision, and
each task uses a deterministic checkpoint key so a replay of the same manifest
cannot spawn duplicate effects.

The runner is a pure, local orchestration function. It does not call GitHub,
Jira, Slack, or production services. It returns the ordered list of per-task
outcomes plus the overall canary result. Side effects (branch/PR/merge) are left
to the bounded node modules and the governance envelope; this runner only
sequences the decisions.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .autonomous_run_checkpoint import capture_autonomous_run, manifest_digest


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _valid_sha(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(ch in "0123456789abcdef" for ch in value)
    )


def _valid_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(ch in "0123456789abcdef" for ch in value[7:])
    )


def run_autonomous_preprod_canary(
    *,
    task_id: str,
    repository: str,
    base_sha: str,
    head_sha: str,
    scope_hash: str,
    run_id: str,
    manifest: Mapping[str, Any],
    evaluate_task: Any,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Execute allowlisted tasks serially and return per-task + overall results.

    ``evaluate_task`` is a callable ``(task_spec, checkpoint) -> dict`` supplied by
    the caller. It must return a mapping with at least ``outcome`` (one of
    COMPLETED / BLOCKED / HUMAN_REQUIRED) and ``reason``. The runner enforces
    serial ordering and fails closed if any task does not reach a terminal,
    allowed state.

    Replay safety: the same manifest + run identity yields an identical
    checkpoint key, so re-invoking the canary cannot create a second run effect.
    """
    if not _valid_sha(base_sha):
        raise ValueError("base_sha must be a 40-char lowercase hex SHA")
    if not _valid_sha(head_sha):
        raise ValueError("head_sha must be a 40-char lowercase hex SHA")
    if not _valid_digest(scope_hash):
        raise ValueError("scope_hash must be a sha256: digest")
    if not isinstance(manifest, Mapping) or not manifest:
        raise ValueError("manifest must be a non-empty mapping")

    tasks = manifest.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("manifest.tasks must be a non-empty list")
    for spec in tasks:
        if not isinstance(spec, Mapping) or not str(spec.get("task_id", "")).strip():
            raise ValueError("each manifest task must carry a non-empty task_id")

    manifest_digest_value = manifest_digest(manifest)
    results: list[dict[str, Any]] = []
    completed_node_ids: list[str] = []
    overall = "COMPLETED"

    for index, spec in enumerate(tasks):
        sub_task_id = str(spec["task_id"])
        checkpoint = capture_autonomous_run(
            task_id=sub_task_id,
            run_id=run_id,
            repository=repository,
            base_sha=base_sha,
            head_sha=head_sha,
            scope_hash=scope_hash,
            manifest=manifest,
            completed_node_ids=completed_node_ids,
            next_node_id=sub_task_id,
            timestamp=observed_at or now_utc(),
        )
        decision = evaluate_task(spec, checkpoint)
        if not isinstance(decision, Mapping):
            decision = {"outcome": "BLOCKED", "reason": "INVALID_TASK_DECISION"}
        outcome = decision.get("outcome")
        entry = {
            "index": index,
            "task_id": sub_task_id,
            "checkpoint_key": checkpoint.checkpoint_key,
            "outcome": outcome,
            "reason": decision.get("reason"),
            "decision": decision,
        }
        results.append(entry)
        if outcome == "COMPLETED":
            completed_node_ids.append(sub_task_id)
            continue
        # Any non-completed task stops the serial canary (fail-closed).
        overall = "BLOCKED" if outcome == "BLOCKED" else "HUMAN_REQUIRED"
        break

    return {
        "schema_version": "1.0",
        "artifact_type": "autonomous-preprod-canary",
        "task_id": task_id,
        "run_id": run_id,
        "repository": repository,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "scope_hash": scope_hash,
        "manifest_digest": manifest_digest_value,
        "task_count": len(tasks),
        "completed_count": len(completed_node_ids),
        "overall_outcome": overall,
        "results": results,
        "authority_granted": False,
        "observed_at": observed_at or now_utc(),
        "result_digest": hashlib.sha256(
            json.dumps(
                {
                    "run_id": run_id,
                    "manifest_digest": manifest_digest_value,
                    "overall_outcome": overall,
                    "task_count": len(tasks),
                    "completed_count": len(completed_node_ids),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
    }


__all__ = ["run_autonomous_preprod_canary"]
