"""Emit durable runtime events into the store."""

from __future__ import annotations

import datetime
from typing import Any, Mapping, Sequence

from runtime.store.sqlite_adapter import SqliteRuntimeStore

RUNTIME_VERSION = "0.1"


class EventEmitter:
    """Append durable runtime events with sequence ordering."""

    def __init__(self, store: SqliteRuntimeStore | None = None) -> None:
        self.store = store or SqliteRuntimeStore()
        self._sequence_cache: dict[str, int] = {}

    def emit(
        self,
        *,
        run_id: str,
        event_type: str,
        node_id: str,
        outcome: str,
        checkpoint_revision: int = 0,
        actor: Mapping[str, Any] | None = None,
        gate: str = "G2_EXECUTION",
        parent_event_id: str | None = None,
        idempotency_key: str | None = None,
        evidence_refs: Sequence[str] | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        actor = actor or {"kind": "node", "id": node_id, "execution_mode": "local_agent"}
        sequence = self._next_sequence(run_id)
        event = {
            "schema_version": "0.1",
            "artifact_type": "durable-event",
            "event_id": f"evt_{run_id}_{sequence}",
            "run_id": run_id,
            "sequence": sequence,
            "parent_event_id": parent_event_id,
            "event_type": event_type,
            "occurred_at_utc": _utcnow(),
            "actor": actor,
            "gate": gate,
            "node_id": node_id,
            "outcome": outcome,
            "runtime_version": RUNTIME_VERSION,
            "node_version": "0.1.0",
            "checkpoint_revision": checkpoint_revision,
            "idempotency_key": idempotency_key,
            "evidence_refs": list(evidence_refs or []),
            "payload": dict(payload or {}),
        }
        self.store.append_event(event)
        return event

    def _next_sequence(self, run_id: str) -> int:
        seq = self._sequence_cache.get(run_id, -1) + 1
        self._sequence_cache[run_id] = seq
        return seq


def _utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()
