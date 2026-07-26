"""Bounded external-write runtime node for GWC.

Implements the P2-I2 SCRUM-108 contract: persist intent before action, bind
idempotency key, enforce exact scope, perform connector call, read back actual
state, reconcile ambiguous timeout, and prevent duplicate side effects.
"""

from __future__ import annotations

import dataclasses
import datetime
import enum
from typing import Any, Mapping, Sequence

from runtime.store.event_emitter import EventEmitter
from runtime.store.pending_action import PendingActionStore, PendingActionResult
from runtime.store.sqlite_adapter import SqliteRuntimeStore

RUNTIME_VERSION = "0.1"


class BoundedExternalWriteOutcome(enum.Enum):
    SUCCESS = "success"
    FAILED_VALIDATION = "failed_validation"
    RETRYABLE_CONFIRMED_NOT_APPLIED = "retryable_confirmed_not_applied"
    PASS_RECONCILED = "pass_reconciled"
    PASS_SINGLE_EFFECT = "pass_single_effect"
    STALE_RECONCILE_REQUIRED = "stale_reconcile_required"
    PASS_AFTER_FENCED_TAKEOVER = "pass_after_fenced_takeover"
    AMBIGUOUS_HUMAN_REQUIRED = "ambiguous_human_required"
    HUMAN_RESOLVED_OR_ABORTED = "human_resolved_or_aborted"


@dataclasses.dataclass(frozen=True)
class BoundedExternalWriteEvidence:
    outcome: BoundedExternalWriteOutcome
    task_id: str
    run_id: str
    node_id: str
    checkpoint_revision: int
    idempotency_key: str | None
    external_reference: str | None
    readback_status: str | None
    attempt_count: int
    reason: str
    events: Sequence[dict[str, Any]] = ()
    pending_action: Mapping[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        data = dataclasses.asdict(self)
        data["outcome"] = self.outcome.value
        return data


class BoundedExternalWriteNode:
    """Execute one bounded external mutation under durable runtime contracts."""

    def __init__(
        self,
        node_id: str = "bounded_external_write",
        node_version: str = "0.1.0",
        store: SqliteRuntimeStore | None = None,
        event_emitter: EventEmitter | None = None,
    ) -> None:
        self.node_id = node_id
        self.node_version = node_version
        self.store = store or SqliteRuntimeStore()
        self.pending_store = PendingActionStore(store=self.store)
        self.event_emitter = event_emitter or EventEmitter(store=self.store)

    def execute(
        self,
        *,
        run_id: str,
        checkpoint_id: str,
        checkpoint_revision: int,
        fencing_token: int,
        task_id: str,
        scope: Mapping[str, Any],
        operation: str,
        payload: Mapping[str, Any],
        connector: Any,
        readback: Any,
        idempotency_key: str | None = None,
        validate: Any | None = None,
        attempt_count: int = 1,
        actor: Mapping[str, Any] | None = None,
    ) -> BoundedExternalWriteEvidence:
        """Run the bounded external-write contract.

        Parameters
        ----------
        run_id, checkpoint_id, checkpoint_revision, fencing_token:
            Durable runtime binding for this execution.
        task_id, scope:
            Exact task and scope enforcement. ``validate`` may reject writes
            that fall outside the declared scope.
        operation, payload:
            The connector operation name and input payload.
        connector:
            Callable that performs the external mutation.  It must accept
            ``operation`` and ``payload`` and return a mapping with at least
            ``external_reference``.
        readback:
            Callable that reads back the actual external state.  It must
            accept ``operation``, ``payload`` and ``external_reference`` and
            return a mapping with ``status`` and optional ``error``.
        idempotency_key:
            Stable key used for pending-action deduplication.
        validate:
            Optional pre-action validator.  When it returns a falsy value
            the node returns ``FAILED_VALIDATION`` without calling
            ``connector``.
        attempt_count:
            Current attempt number for the pending action.
        actor:
            Runtime actor metadata for emitted events.
        """
        actor = actor or {"kind": "node", "id": self.node_id, "execution_mode": "local_agent"}

        self.event_emitter.emit(
            run_id=run_id,
            event_type="node_started",
            node_id=self.node_id,
            outcome="pending",
            checkpoint_revision=checkpoint_revision,
            actor=actor,
            gate="G2_EXECUTION",
            payload={"operation": operation, "idempotency_key": idempotency_key},
        )

        if validate and not validate(scope=scope, operation=operation, payload=payload):
            evidence = BoundedExternalWriteEvidence(
                outcome=BoundedExternalWriteOutcome.FAILED_VALIDATION,
                task_id=task_id,
                run_id=run_id,
                node_id=self.node_id,
                checkpoint_revision=checkpoint_revision,
                idempotency_key=idempotency_key,
                external_reference=None,
                readback_status="rejected",
                attempt_count=attempt_count,
                reason="pre-action validation rejected the bounded write",
            )
            self.event_emitter.emit(
                run_id=run_id,
                event_type="node_completed",
                node_id=self.node_id,
                outcome="failure",
                checkpoint_revision=checkpoint_revision,
                actor=actor,
                gate="G2_EXECUTION",
                payload=evidence.as_dict(),
            )
            return evidence

        pending: PendingActionResult | None = None
        if idempotency_key is not None:
            pending = self.pending_store.submit(
                run_id=run_id,
                adapter_id=self.node_id,
                operation=operation,
                idempotency_key=idempotency_key,
                payload={"scope": dict(scope), "payload": dict(payload)},
            )

        connector_error: str | None = None
        external_reference: str | None = None
        try:
            connector_result = connector(operation=operation, payload=payload, idempotency_key=idempotency_key)
            external_reference = connector_result.get("external_reference") if isinstance(connector_result, Mapping) else None
        except Exception as exc:  # pylint: disable=broad-except
            connector_error = f"{type(exc).__name__}: {exc}"

        if pending is not None:
            self.pending_store.mark_unknown_if_unresolved(
                action_id=pending.action_id,
                run_id=run_id,
                error=connector_error,
            )

        if connector_error is not None:
            evidence = BoundedExternalWriteEvidence(
                outcome=BoundedExternalWriteOutcome.RETRYABLE_CONFIRMED_NOT_APPLIED,
                task_id=task_id,
                run_id=run_id,
                node_id=self.node_id,
                checkpoint_revision=checkpoint_revision,
                idempotency_key=idempotency_key,
                external_reference=external_reference,
                readback_status="rejected",
                attempt_count=attempt_count,
                reason=f"connector call failed before effect could be confirmed: {connector_error}",
                pending_action=_dataclass_asdict(pending) if pending else None,
            )
            self.event_emitter.emit(
                run_id=run_id,
                event_type="side_effect_failed",
                node_id=self.node_id,
                outcome="failure",
                checkpoint_revision=checkpoint_revision,
                actor=actor,
                gate="G2_EXECUTION",
                idempotency_key=idempotency_key,
                payload=evidence.as_dict(),
            )
            return evidence

        readback_result = readback(operation=operation, payload=payload, external_reference=external_reference)
        readback_status = readback_result.get("status") if isinstance(readback_result, Mapping) else None
        readback_error = readback_result.get("error") if isinstance(readback_result, Mapping) else None

        if pending is not None:
            if readback_status == "confirmed":
                self.pending_store.mark_succeeded(
                    action_id=pending.action_id,
                    run_id=run_id,
                    external_reference=external_reference,
                    readback_evidence_refs=[f"readback:{run_id}:{pending.action_id}"],
                )
            else:
                self.pending_store.mark_failed(
                    action_id=pending.action_id,
                    run_id=run_id,
                    external_reference=external_reference,
                    error=readback_error or "readback did not confirm effect",
                )

        outcome = self._resolve_outcome(
            readback_status=readback_status,
            readback_error=readback_error,
            external_reference=external_reference,
            attempt_count=attempt_count,
        )

        evidence = BoundedExternalWriteEvidence(
            outcome=outcome,
            task_id=task_id,
            run_id=run_id,
            node_id=self.node_id,
            checkpoint_revision=checkpoint_revision,
            idempotency_key=idempotency_key,
            external_reference=external_reference,
            readback_status=readback_status,
            attempt_count=attempt_count,
            reason=self._outcome_reason(outcome, readback_status, readback_error, external_reference),
            pending_action=_dataclass_asdict(pending) if pending else None,
        )

        event_type = "side_effect_completed" if outcome == BoundedExternalWriteOutcome.SUCCESS else "side_effect_failed"
        self.event_emitter.emit(
            run_id=run_id,
            event_type=event_type,
            node_id=self.node_id,
            outcome="success" if outcome == BoundedExternalWriteOutcome.SUCCESS else "failure",
            checkpoint_revision=checkpoint_revision,
            actor=actor,
            gate="G2_EXECUTION",
            idempotency_key=idempotency_key,
            payload=evidence.as_dict(),
        )

        return evidence

    def handle_request(self, request: Mapping[str, Any]) -> dict[str, Any]:
        node_request = request.get("request", {})
        evidence = self.execute(
            run_id=node_request.get("run_id", ""),
            checkpoint_id=node_request.get("checkpoint_id", ""),
            checkpoint_revision=int(node_request.get("checkpoint_revision", 0)),
            fencing_token=int(node_request.get("fencing_token", 0)),
            task_id=node_request.get("task_id", ""),
            scope=node_request.get("scope", {}),
            operation=node_request.get("operation", ""),
            payload=node_request.get("payload", {}),
            connector=node_request.get("connector", lambda **kwargs: {}),
            readback=node_request.get("readback", lambda **kwargs: {"status": "pending"}),
            idempotency_key=node_request.get("idempotency_key"),
            validate=node_request.get("validate"),
            attempt_count=int(node_request.get("attempt_count", 1)),
        )
        return {
            "schema_version": "0.1",
            "artifact_type": "adapter-contract",
            "adapter_id": self.node_id,
            "adapter_version": self.node_version,
            "capabilities": {
                "side_effects": True,
                "idempotency": True,
                "readback": True,
            },
            "request": node_request,
            "result": {
                "outcome": evidence.outcome.value,
                "adapter_version": self.node_version,
                "readback_status": evidence.readback_status or "rejected",
                "evidence_refs": [f"evt:{evidence.run_id}:{evidence.node_id}"],
                "error_code": None if evidence.outcome == BoundedExternalWriteOutcome.SUCCESS else "bounded_write_failed",
            },
        }

    def _resolve_outcome(
        self,
        *,
        readback_status: str | None,
        readback_error: str | None,
        external_reference: str | None,
        attempt_count: int,
    ) -> BoundedExternalWriteOutcome:
        if readback_status == "confirmed":
            return BoundedExternalWriteOutcome.SUCCESS
        if readback_status == "rejected":
            if external_reference and attempt_count > 1:
                return BoundedExternalWriteOutcome.AMBIGUOUS_HUMAN_REQUIRED
            return BoundedExternalWriteOutcome.RETRYABLE_CONFIRMED_NOT_APPLIED
        if readback_status == "pending" or readback_error:
            return BoundedExternalWriteOutcome.AMBIGUOUS_HUMAN_REQUIRED
        return BoundedExternalWriteOutcome.AMBIGUOUS_HUMAN_REQUIRED

    def _outcome_reason(
        self,
        outcome: BoundedExternalWriteOutcome,
        readback_status: str | None,
        readback_error: str | None,
        external_reference: str | None,
    ) -> str:
        if outcome == BoundedExternalWriteOutcome.SUCCESS:
            return "bounded external effect was confirmed by readback"
        if outcome == BoundedExternalWriteOutcome.FAILED_VALIDATION:
            return "pre-action validation rejected the write"
        if outcome == BoundedExternalWriteOutcome.RETRYABLE_CONFIRMED_NOT_APPLIED:
            return "readback rejected the effect; no confirmed external state"
        if outcome == BoundedExternalWriteOutcome.AMBIGUOUS_HUMAN_REQUIRED:
            return f"readback was ambiguous; human resolution required; error={readback_error}"
        return f"terminal outcome={outcome.value}"


def _dataclass_asdict(obj: Any) -> dict[str, Any]:
    if obj is None:
        return None
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    return dict(obj) if isinstance(obj, Mapping) else obj
