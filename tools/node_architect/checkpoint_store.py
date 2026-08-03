#!/usr/bin/env python3
"""Replay-safe checkpoint persistence primitives for GWC node execution.

The module is local and data-oriented. It does not call GitHub, Jira, Slack,
or production services. Legacy callers retain revision-only CAS behavior;
strict callers supply ``cas_context`` and receive the SCRUM-208 binding guard
before any event/checkpoint mutation.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from tools.node_architect.cas_write_guard import evaluate_cas_write


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest_payload(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CheckpointInput:
    task_id: str
    run_id: str
    node_id: str
    repository: str
    branch: str
    base_sha: str
    head_sha: str
    scope_hash: str
    state: dict[str, Any]
    expected_revision: int | None = None
    graph_revision: str | None = None
    lease_id: str | None = None
    fencing_token: str | int | None = None
    cas_context: dict[str, Any] | None = None


class CheckpointConflict(RuntimeError):
    """Raised when a checkpoint write fails its CAS/binding guard."""

    def __init__(self, message: str, *, decision: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.decision = dict(decision) if isinstance(decision, Mapping) else None


def empty_store() -> dict[str, Any]:
    return {"schema_version": "1.0", "artifact_type": "runtime-checkpoint-store", "revision": 0, "events": [], "checkpoints": {}, "effects": {}}


def load_store(path: Path) -> dict[str, Any]:
    if not path.exists():
        return empty_store()
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("checkpoint store must be a JSON object")
    payload.setdefault("schema_version", "1.0")
    payload.setdefault("artifact_type", "runtime-checkpoint-store")
    payload.setdefault("revision", 0)
    payload.setdefault("events", [])
    payload.setdefault("checkpoints", {})
    payload.setdefault("effects", {})
    return payload


def write_store(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def checkpoint_key(task_id: str, run_id: str, node_id: str) -> str:
    return f"{task_id}:{run_id}:{node_id}"


def evaluate_checkpoint_guard(store: Mapping[str, Any], item: CheckpointInput) -> dict[str, Any] | None:
    """Evaluate strict CAS context, returning None for legacy callers."""
    if item.cas_context is None:
        return None
    if not isinstance(item.cas_context, Mapping):
        raise CheckpointConflict("INVALID_INPUT cas_context must be an object")
    context = dict(item.cas_context)
    context.setdefault("task_id", item.task_id)
    context.setdefault("repository", item.repository)
    context.setdefault("branch", item.branch)
    context.setdefault("base_sha", item.base_sha)
    context.setdefault("scope_hash", item.scope_hash)
    context.setdefault("expected_revision", item.expected_revision)
    context["observed_revision"] = int(store.get("revision", 0))
    context["latest_observed_state"] = {
        "revision": int(store.get("revision", 0)),
        "checkpoints": store.get("checkpoints", {}),
        "store_digest": store.get("store_digest"),
    }
    context["committed_effects"] = store.get("effects", {})
    return evaluate_cas_write(context)


def persist_checkpoint(store: dict[str, Any], item: CheckpointInput, *, committed_at: str | None = None) -> dict[str, Any]:
    current_revision = int(store.get("revision", 0))
    decision = evaluate_checkpoint_guard(store, item)
    if decision is not None:
        if decision["outcome"] == "DUPLICATE_EFFECT_REPLAYED":
            return store
        if not decision["may_write"]:
            raise CheckpointConflict(f"{decision['outcome']} reasons={','.join(decision['reason_codes'])}", decision=decision)
    elif item.expected_revision is not None and item.expected_revision != current_revision:
        raise CheckpointConflict(f"CAS_MISMATCH expected={item.expected_revision} actual={current_revision}")

    committed_at = committed_at or _now()
    key = checkpoint_key(item.task_id, item.run_id, item.node_id)
    state_digest = digest_payload(item.state)
    next_revision = current_revision + 1
    record = {
        "schema_version": "1.0", "artifact_type": "runtime-checkpoint",
        "task_id": item.task_id, "run_id": item.run_id, "node_id": item.node_id,
        "repository": item.repository, "branch": item.branch, "base_sha": item.base_sha,
        "head_sha": item.head_sha, "scope_hash": item.scope_hash,
        "graph_revision": item.graph_revision, "lease_id": item.lease_id,
        "fencing_token": item.fencing_token, "revision": next_revision,
        "previous_revision": current_revision, "state": item.state,
        "state_digest": state_digest, "committed_at": committed_at,
    }
    if decision is not None:
        record["cas_decision_digest"] = decision["decision_digest"]
        record["cas_outcome"] = decision["outcome"]
    event = {
        "schema_version": "1.0", "artifact_type": "runtime-event",
        "event_type": "checkpoint.persisted", "task_id": item.task_id,
        "run_id": item.run_id, "node_id": item.node_id,
        "repository": item.repository, "branch": item.branch,
        "head_sha": item.head_sha, "scope_hash": item.scope_hash,
        "revision": next_revision, "state_digest": state_digest,
        "occurred_at": committed_at,
    }
    if decision is not None:
        event["cas_decision_digest"] = decision["decision_digest"]
    event["event_digest"] = digest_payload(event)
    store["revision"] = next_revision
    store.setdefault("events", []).append(event)
    store.setdefault("checkpoints", {})[key] = record
    if decision is not None:
        store.setdefault("effects", {})[decision["idempotency_key"]] = {
            "checkpoint_key": key, "revision": next_revision,
            "state_digest": state_digest, "cas_decision_digest": decision["decision_digest"],
            "committed_at": committed_at,
        }
    store["store_digest"] = digest_payload({"revision": store["revision"], "events": store["events"], "checkpoints": store["checkpoints"], "effects": store.get("effects", {})})
    return store


def persist_to_file(path: Path, item: CheckpointInput) -> dict[str, Any]:
    store = load_store(path)
    updated = persist_checkpoint(store, item)
    write_store(path, updated)
    return updated


def replay_checkpoint(store: dict[str, Any], task_id: str, run_id: str, node_id: str) -> dict[str, Any] | None:
    return store.get("checkpoints", {}).get(checkpoint_key(task_id, run_id, node_id))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Persist a GWC runtime checkpoint JSON payload.")
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--payload", type=Path, required=True)
    args = parser.parse_args(argv)
    item = CheckpointInput(**json.loads(args.payload.read_text(encoding="utf-8")))
    updated = persist_to_file(args.store, item)
    print(json.dumps({"outcome": "PASS", "revision": updated["revision"], "store_digest": updated["store_digest"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
