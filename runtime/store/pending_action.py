"""Pending action state machine and persistence helpers."""

from __future__ import annotations

import dataclasses
import datetime
from typing import Any, Mapping, Sequence

from runtime.store.sqlite_adapter import SqliteRuntimeStore

RUNTIME_VERSION = "0.1"


def _utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class PendingActionStore:
    """Manage pending actions through their state machine."""

    VALID_TRANSITIONS = {
        "pending": {"claimed", "failed", "cancelled"},
        "claimed": {"executing", "failed", "cancelled"},
        "executing": {"succeeded", "failed", "unknown", "cancelled"},
        "succeeded": set(),
        "failed": set(),
        "unknown": {"reconciled", "failed", "cancelled"},
        "reconciled": set(),
        "cancelled": set(),
    }

    def __init__(self, store: SqliteRuntimeStore | None = None) -> None:
        self.store = store or SqliteRuntimeStore()

    def submit(
        self,
        *,
        run_id: str,
        adapter_id: str,
        operation: str,
        idempotency_key: str,
        payload: Mapping[str, Any],
        action_id: str | None = None,
    ) -> PendingActionResult:
        action_id = action_id or f"act_{idempotency_key}"
        existing = self.store.find_pending_action_by_idempotency_key(run_id, idempotency_key)
        if existing and existing["status"] in {"pending", "claimed", "executing", "unknown"}:
            return PendingActionResult(
                action_id=existing["action_id"],
                run_id=existing["run_id"],
                adapter_id=existing["adapter_id"],
                operation=existing["operation"],
                idempotency_key=existing["idempotency_key"],
                status=existing["status"],
                attempt_count=existing["attempt_count"],
                readback_status=existing["readback_status"],
                external_reference=existing["external_reference"],
                readback_evidence_refs=existing["readback_evidence_refs"],
                last_error=existing["last_error"],
                requested_at_utc=existing["requested_at_utc"],
                updated_at_utc=existing["updated_at_utc"],
                payload=existing["payload"],
            )

        now = _utcnow()
        action = {
            "schema_version": "0.1",
            "artifact_type": "pending-action",
            "action_id": action_id,
            "run_id": run_id,
            "adapter_id": adapter_id,
            "operation": operation,
            "idempotency_key": idempotency_key,
            "status": "pending",
            "attempt_count": 1,
            "readback_required": True,
            "readback_status": "pending",
            "external_reference": None,
            "readback_evidence_refs": [],
            "last_error": None,
            "requested_at_utc": now,
            "updated_at_utc": now,
            "payload": dict(payload),
        }
        self.store.submit_pending_action(action)
        return PendingActionResult(
            action_id=action["action_id"],
            run_id=action["run_id"],
            adapter_id=action["adapter_id"],
            operation=action["operation"],
            idempotency_key=action["idempotency_key"],
            status=action["status"],
            attempt_count=action["attempt_count"],
            readback_status=action["readback_status"],
            external_reference=action["external_reference"],
            readback_evidence_refs=action["readback_evidence_refs"],
            last_error=action["last_error"],
            requested_at_utc=action["requested_at_utc"],
            updated_at_utc=action["updated_at_utc"],
            payload=action["payload"],
        )

    def claim(self, action_id: str, run_id: str) -> bool:
        return self._transition(action_id, run_id, "pending", "claimed")

    def mark_executing(self, action_id: str, run_id: str) -> bool:
        current = self.store.read_pending_action(action_id)
        if not current:
            return False
        return self._transition(action_id, run_id, current["status"], "executing")

    def mark_succeeded(
        self,
        action_id: str,
        run_id: str,
        external_reference: str | None = None,
        readback_evidence_refs: Sequence[str] | None = None,
    ) -> bool:
        current = self.store.read_pending_action(action_id)
        if not current:
            return False
        if not self._transition(action_id, run_id, current["status"], "succeeded"):
            return False
        updates: dict[str, Any] = {"readback_status": "confirmed"}
        if external_reference is not None:
            updates["external_reference"] = external_reference
        if readback_evidence_refs:
            updates["readback_evidence_refs"] = list(readback_evidence_refs)
        self.store.update_pending_action(action_id, updates)
        return True

    def mark_failed(
        self,
        action_id: str,
        run_id: str,
        error: str | None = None,
        external_reference: str | None = None,
    ) -> bool:
        current = self.store.read_pending_action(action_id)
        if not current:
            return False
        target = "failed"
        if current["status"] == "unknown":
            target = "failed"
        if not self._transition(action_id, run_id, current["status"], target):
            return False
        updates: dict[str, Any] = {"readback_status": "rejected"}
        if error:
            updates["last_error"] = error
        if external_reference is not None:
            updates["external_reference"] = external_reference
        self.store.update_pending_action(action_id, updates)
        return True

    def mark_unknown_if_unresolved(self, action_id: str, run_id: str, error: str | None = None) -> bool:
        current = self.store.read_pending_action(action_id)
        if not current:
            return False
        if current["status"] in {"succeeded", "failed", "reconciled", "cancelled"}:
            return False
        updates: dict[str, Any] = {"status": "unknown"}
        if error:
            updates["last_error"] = error
        self.store.update_pending_action(action_id, updates)
        return True

    def mark_reconciled(self, action_id: str, run_id: str, readback_evidence_refs: Sequence[str] | None = None) -> bool:
        current = self.store.read_pending_action(action_id)
        if not current:
            return False
        if not self._transition(action_id, run_id, current["status"], "reconciled"):
            return False
        updates = {"readback_status": "confirmed"}
        if readback_evidence_refs:
            updates["readback_evidence_refs"] = list(readback_evidence_refs)
        self.store.update_pending_action(action_id, updates)
        return True

    def cancel(self, action_id: str, run_id: str) -> bool:
        current = self.store.read_pending_action(action_id)
        if not current:
            return False
        if current["status"] in {"succeeded", "failed", "reconciled", "cancelled"}:
            return False
        return self._transition(action_id, run_id, current["status"], "cancelled")

    def _transition(self, action_id: str, run_id: str, current: str, target: str) -> bool:
        if target not in self.VALID_TRANSITIONS.get(current, set()):
            return False
        return self.store.update_pending_action(action_id, {"status": target})


@dataclasses.dataclass(frozen=True)
class PendingActionResult:
    action_id: str
    run_id: str
    adapter_id: str
    operation: str
    idempotency_key: str
    status: str
    attempt_count: int
    readback_status: str
    external_reference: str | None
    readback_evidence_refs: Sequence[str]
    last_error: str | None
    requested_at_utc: str
    updated_at_utc: str
    payload: Mapping[str, Any]
