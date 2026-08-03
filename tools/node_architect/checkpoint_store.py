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
    return {
        "schema_version": "1.0",
        "artifact_type": "runtime-checkpoint-store",
        "revision": 0,
        "events": [],
        "checkpoints": {},
        "effects": {},
        "lease_binding": None,
    }


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
    payload.setdefault("lease_binding", None)
    return payload


def write_store(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def checkpoint_key(task_id: str, run_id: str, node_id: str) -> str:
    return f"{task_id}:{run_id}:{node_id}"


def _item_binding(item: CheckpointInput) -> dict[str, Any]:
    return {
        "task_id": item.task_id,
        "repository": item.repository,
        "branch": item.branch,
        "base_sha": item.base_sha,
        "scope_hash": item.scope_hash,
    }


def _authoritative_store_binding(store: Mapping[str, Any], item: CheckpointInput) -> tuple[dict[str, Any], list[str]]:
    binding = store.get("binding")
    if isinstance(binding, Mapping):
        return dict(binding), []

    checkpoint_bindings: set[str] = set()
    binding_payloads: dict[str, dict[str, Any]] = {}
    checkpoints = store.get("checkpoints", {})
    if isinstance(checkpoints, Mapping):
        for record in checkpoints.values():
            if not isinstance(record, Mapping):
                continue
            candidate = {field: record.get(field) for field in ("task_id", "repository", "branch", "base_sha", "scope_hash")}
            if all(isinstance(value, str) and value for value in candidate.values()):
                rendered = canonical_json(candidate)
                checkpoint_bindings.add(rendered)
                binding_payloads[rendered] = candidate
    if len(checkpoint_bindings) == 1:
        rendered = next(iter(checkpoint_bindings))
        return binding_payloads[rendered], []
    if len(checkpoint_bindings) > 1:
        return _item_binding(item), ["STORE_BINDING_AMBIGUOUS"]
    return _item_binding(item), []



def _requested_lease_binding(item: CheckpointInput, supplied: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lease_owner": supplied.get("lease_owner"),
        "lease_token": item.lease_id,
        "fencing_token": item.fencing_token,
        "lease_expires_at": supplied.get("lease_expires_at"),
    }


def _valid_lease_binding(binding: Mapping[str, Any]) -> bool:
    return (
        isinstance(binding.get("lease_owner"), str)
        and bool(str(binding.get("lease_owner")).strip())
        and isinstance(binding.get("lease_token"), str)
        and bool(str(binding.get("lease_token")).strip())
        and isinstance(binding.get("fencing_token"), int)
        and not isinstance(binding.get("fencing_token"), bool)
        and int(binding.get("fencing_token")) >= 0
        and isinstance(binding.get("lease_expires_at"), str)
        and bool(str(binding.get("lease_expires_at")).strip())
    )


def _authoritative_lease_binding(
    store: Mapping[str, Any], item: CheckpointInput, supplied: Mapping[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Resolve current lease authority from persisted state, bootstrapping only an empty store."""
    requested = _requested_lease_binding(item, supplied)
    binding = store.get("lease_binding")
    if isinstance(binding, Mapping):
        authoritative = dict(binding)
        if not _valid_lease_binding(authoritative):
            return requested, ["STORE_LEASE_BINDING_INVALID"]
        return authoritative, []

    has_runtime_state = (
        int(store.get("revision", 0)) > 0
        or bool(store.get("events"))
        or bool(store.get("checkpoints"))
        or bool(store.get("effects"))
    )
    if has_runtime_state:
        return requested, ["STORE_LEASE_BINDING_MISSING"]
    return requested, []


def _prepare_cas_context(
    store: Mapping[str, Any], item: CheckpointInput, *, evaluation_time: str | None = None
) -> dict[str, Any] | None:
    if item.cas_context is None:
        return None
    if not isinstance(item.cas_context, Mapping):
        raise CheckpointConflict("INVALID_INPUT cas_context must be an object")

    supplied = dict(item.cas_context)
    context = dict(supplied)
    errors: list[str] = []
    canonical_expected = {
        "task_id": item.task_id,
        "repository": item.repository,
        "branch": item.branch,
        "base_sha": item.base_sha,
        "scope_hash": item.scope_hash,
        "expected_revision": item.expected_revision,
        "lease_token": item.lease_id,
        "fencing_token": item.fencing_token,
        "checkpoint_key": checkpoint_key(item.task_id, item.run_id, item.node_id),
        "run_id": item.run_id,
        "checkpoint_node_id": item.node_id,
    }
    for field, expected in canonical_expected.items():
        if expected is None:
            continue
        if field in supplied and supplied[field] != expected:
            errors.append(f"CONTEXT_ITEM_CONFLICT:{field}")
        context[field] = expected

    authoritative, store_errors = _authoritative_store_binding(store, item)
    errors.extend(store_errors)
    observed_fields = {
        "observed_task_id": authoritative["task_id"],
        "observed_repository": authoritative["repository"],
        "observed_branch": authoritative["branch"],
        "observed_base_sha": authoritative["base_sha"],
        "observed_scope_hash": authoritative["scope_hash"],
    }
    for field, observed in observed_fields.items():
        if field in supplied and supplied[field] != observed:
            errors.append(f"CONTEXT_OBSERVED_BINDING_CONFLICT:{field}")
        context[field] = observed

    lease_authority, lease_errors = _authoritative_lease_binding(store, item, supplied)
    errors.extend(lease_errors)
    context["observed_lease_owner"] = lease_authority.get("lease_owner")
    context["observed_lease_token"] = lease_authority.get("lease_token")
    context["observed_fencing_token"] = lease_authority.get("fencing_token")
    context["lease_expires_at"] = lease_authority.get("lease_expires_at")
    context["observed_at"] = evaluation_time or _now()

    context["observed_revision"] = int(store.get("revision", 0))
    context["latest_observed_state"] = {
        "revision": int(store.get("revision", 0)),
        "binding": authoritative,
        "lease_binding": lease_authority,
        "checkpoints": store.get("checkpoints", {}),
        "store_digest": store.get("store_digest"),
    }
    context["committed_effects"] = store.get("effects", {})
    context["precondition_errors"] = sorted(set(errors))
    return context


def evaluate_checkpoint_guard(
    store: Mapping[str, Any], item: CheckpointInput, *, evaluation_time: str | None = None
) -> dict[str, Any] | None:
    """Evaluate strict CAS context, returning None for legacy callers."""
    context = _prepare_cas_context(store, item, evaluation_time=evaluation_time)
    return None if context is None else evaluate_cas_write(context)


def _effect_binding(item: CheckpointInput, context: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "task_id": item.task_id,
        "repository": item.repository,
        "branch": item.branch,
        "base_sha": item.base_sha,
        "scope_hash": item.scope_hash,
        "checkpoint_key": checkpoint_key(item.task_id, item.run_id, item.node_id),
        "run_id": item.run_id,
        "checkpoint_node_id": item.node_id,
        "lease_owner": context["lease_owner"],
        "lease_token": context["lease_token"],
        "fencing_token": context["fencing_token"],
        "lease_expires_at": context["lease_expires_at"],
        "idempotency_key": context["idempotency_key"],
        "expected_revision": item.expected_revision,
    }


def persist_checkpoint(
    store: dict[str, Any], item: CheckpointInput, *,
    committed_at: str | None = None, evaluation_time: str | None = None,
) -> dict[str, Any]:
    current_revision = int(store.get("revision", 0))
    context = _prepare_cas_context(store, item, evaluation_time=evaluation_time)
    decision = None if context is None else evaluate_cas_write(context)
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
    if decision is not None and context is not None:
        store.setdefault("binding", _item_binding(item))
        if not isinstance(store.get("lease_binding"), Mapping):
            store["lease_binding"] = {
                "lease_owner": context["observed_lease_owner"],
                "lease_token": context["observed_lease_token"],
                "fencing_token": context["observed_fencing_token"],
                "lease_expires_at": context["lease_expires_at"],
            }
        store.setdefault("effects", {})[decision["idempotency_key"]] = {
            "binding": _effect_binding(item, context),
            "checkpoint_key": key,
            "revision": next_revision,
            "state_digest": state_digest,
            "cas_decision_digest": decision["decision_digest"],
            "committed_at": committed_at,
        }
    store["store_digest"] = digest_payload({
        "revision": store["revision"],
        "binding": store.get("binding"),
        "lease_binding": store.get("lease_binding"),
        "events": store["events"],
        "checkpoints": store["checkpoints"],
        "effects": store.get("effects", {}),
    })
    return store


def persist_to_file(
    path: Path, item: CheckpointInput, *, evaluation_time: str | None = None
) -> dict[str, Any]:
    store = load_store(path)
    updated = persist_checkpoint(store, item, evaluation_time=evaluation_time)
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
