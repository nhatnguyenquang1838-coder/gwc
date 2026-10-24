"""Universal Runtime v2 stateless action Executor.

The Executor accepts one immutable native assignment, invokes one provider action,
and emits only a sealed actor receipt. It never reads or advances RunState and has
no import path to Controller continuation, mailbox history, or GWC v1 runtime.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping

from .universal_run_kernel import GATES
from .universal_runtime_profile import load_universal_v2_default_profile

UNIVERSAL_RUN_NEW_RUNTIME = "UNIVERSAL_RUN_NEW_RUNTIME"
_FORBIDDEN_CONTROL_FIELDS = {
    "typed_next", "successor_run_state", "controller_decision", "next_gate",
    "active_gate", "history_controller", "mailbox_expected_executor_seq",
    "expected_executor_seq", "controller_seq", "mailbox_ref", "transport_profile",
}


class UniversalRunExecutionError(ValueError):
    """Fail-closed Universal Executor assignment/action error."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        super().__init__(f"{code}: {detail}" if detail else code)


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _digest(value: Mapping[str, Any], digest_field: str | None = None) -> str:
    subject = {key: item for key, item in value.items() if key != digest_field} if digest_field else dict(value)
    return "sha256:" + hashlib.sha256(_canonical_bytes(subject)).hexdigest()


def _safe_segment(value: str) -> str:
    segment = re.sub(r"[^A-Za-z0-9._-]", "_", value)
    if not segment or segment in {".", ".."}:
        raise UniversalRunExecutionError("EXECUTOR_PATH_SEGMENT_INVALID")
    return segment


class UniversalExecutor:
    """Stateless actor. Lifecycle decisions belong exclusively to UniversalController."""

    def execute(
        self,
        *,
        assignment: Mapping[str, Any],
        provider: Any,
        event: Mapping[str, Any],
        evidence_root: Path | str,
        max_iterations: int = 32,
    ) -> dict[str, Any]:
        profile = load_universal_v2_default_profile()
        if not isinstance(assignment, Mapping) or not isinstance(event, Mapping):
            raise UniversalRunExecutionError("EXECUTOR_INPUT_INVALID")
        if set(assignment) & _FORBIDDEN_CONTROL_FIELDS:
            raise UniversalRunExecutionError("EXECUTOR_ASSIGNMENT_HAS_CONTROLLER_FIELDS")
        if set(event) & _FORBIDDEN_CONTROL_FIELDS:
            raise UniversalRunExecutionError("EXECUTOR_EVENT_HAS_TRANSPORT_CONTROL_FIELDS")
        if assignment.get("schema_id") != "gwc.universal-run.executor-assignment.v2" or assignment.get("schema_version") != 2:
            raise UniversalRunExecutionError("EXECUTOR_ASSIGNMENT_SCHEMA_MISMATCH")
        if assignment.get("runtime_protocol") != profile["runtime_protocol"]:
            raise UniversalRunExecutionError("EXECUTOR_PROTOCOL_MISMATCH")
        if assignment.get("runtime_epoch") != profile["runtime_epoch"]:
            raise UniversalRunExecutionError("EXECUTOR_EPOCH_MISMATCH")
        if assignment.get("runtime_profile_digest") != profile["profile_digest"]:
            raise UniversalRunExecutionError("EXECUTOR_PROFILE_MISMATCH")
        if assignment.get("actor") != "EXECUTOR" or assignment.get("effect_authority") != "NONE":
            raise UniversalRunExecutionError("EXECUTOR_AUTHORITY_BOUNDARY_VIOLATION")
        if assignment.get("authority_decision_ref") is not None:
            raise UniversalRunExecutionError("EXECUTOR_AUTHORITY_REFERENCE_FORBIDDEN")
        if assignment.get("gate") not in GATES:
            raise UniversalRunExecutionError("EXECUTOR_GATE_INVALID")
        if assignment.get("runtime_plan_digest") is None or assignment.get("assignment_digest") != _digest(assignment, "assignment_digest"):
            raise UniversalRunExecutionError("EXECUTOR_ASSIGNMENT_DIGEST_INVALID")
        if not isinstance(max_iterations, int) or isinstance(max_iterations, bool) or max_iterations < 1:
            raise UniversalRunExecutionError("EXECUTOR_ITERATION_LIMIT_INVALID")
        if not isinstance(getattr(provider, "name", None), str) or not provider.name:
            raise UniversalRunExecutionError("EXECUTOR_PROVIDER_INVALID")
        run = getattr(provider, "run", None)
        if not callable(run):
            raise UniversalRunExecutionError("EXECUTOR_PROVIDER_ACTION_UNAVAILABLE")

        request = dict(assignment)
        request["event"] = dict(event)
        request["max_iterations"] = max_iterations
        try:
            provider_result = run(request)
        except Exception as exc:  # noqa: BLE001 - an actor failure is not a Controller transition
            raise UniversalRunExecutionError("EXECUTOR_PROVIDER_ACTION_FAILED", type(exc).__name__) from exc
        if not isinstance(provider_result, Mapping):
            raise UniversalRunExecutionError("EXECUTOR_PROVIDER_RESULT_INVALID")
        forbidden_result = set(provider_result) & _FORBIDDEN_CONTROL_FIELDS
        if forbidden_result:
            raise UniversalRunExecutionError("EXECUTOR_RESULT_CONTROL_FIELD_FORBIDDEN", ",".join(sorted(forbidden_result)))
        if "authority_granted" in provider_result or "executed_effects" in provider_result:
            raise UniversalRunExecutionError("EXECUTOR_RESULT_EFFECT_FIELD_FORBIDDEN")
        result_body = dict(provider_result)
        try:
            result_digest = _digest(result_body)
        except (TypeError, ValueError) as exc:
            raise UniversalRunExecutionError("EXECUTOR_PROVIDER_RESULT_NOT_JSON") from exc
        action_outcome = str(provider_result.get("outcome", "")).upper()
        host_status = "ACTION_COMPLETE" if action_outcome == "PASS" else "ACTION_BLOCKED"
        if host_status != "ACTION_COMPLETE":
            raise UniversalRunExecutionError("EXECUTOR_ACTION_NOT_COMPLETE", action_outcome or "MISSING_OUTCOME")

        evidence_root_path = Path(evidence_root).expanduser().resolve()
        run_id = _safe_segment(str(assignment["run_id"]))
        idempotency = str(assignment["idempotency_key"])
        key = _safe_segment(idempotency.split(":")[-1][:24])
        relative_ref = Path(run_id) / key / "executor-action-receipt.json"
        receipt_body = {
            "schema_id": "gwc.universal-run.executor-action-receipt.v2",
            "schema_version": 2,
            "artifact_type": "executor-action-receipt",
            "runtime_protocol": profile["runtime_protocol"],
            "runtime_epoch": profile["runtime_epoch"],
            "runtime_profile_digest": profile["profile_digest"],
            "route_id": UNIVERSAL_RUN_NEW_RUNTIME,
            "run_id": assignment["run_id"],
            "sequence": assignment["sequence"],
            "gate": assignment["gate"],
            "action": assignment["action"],
            "actor": "EXECUTOR",
            "node_id": assignment["node_id"],
            "node_allocation_id": assignment["node_allocation_id"],
            "runtime_plan_digest": assignment["runtime_plan_digest"],
            "assignment_digest": assignment["assignment_digest"],
            "event_id": idempotency,
            "host_status": host_status,
            "host_result_digest": result_digest,
            "evidence_refs": {"executor_receipt": relative_ref.as_posix()},
            "authority_granted": False,
            "executed_effects": [],
        }
        receipt = {**receipt_body, "receipt_digest": _digest(receipt_body)}
        receipt_path = evidence_root_path / relative_ref
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(receipt, indent=2, ensure_ascii=False) + "\n"
        if receipt_path.exists():
            try:
                existing = json.loads(receipt_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise UniversalRunExecutionError("EXECUTOR_IDEMPOTENCY_CONFLICT") from exc
            if existing != receipt:
                raise UniversalRunExecutionError("EXECUTOR_IDEMPOTENCY_CONFLICT")
            return receipt
        temp_path = receipt_path.with_suffix(".json.tmp")
        try:
            with temp_path.open("x", encoding="utf-8") as handle:
                handle.write(serialized)
            os.replace(temp_path, receipt_path)
        except FileExistsError as exc:
            raise UniversalRunExecutionError("EXECUTOR_IDEMPOTENCY_CONFLICT") from exc
        finally:
            if temp_path.exists():
                temp_path.unlink()
        return receipt


def execute_universal_run_node(
    *, assignment: Mapping[str, Any], provider: Any, event: Mapping[str, Any],
    evidence_root: Path | str, max_iterations: int = 32,
) -> dict[str, Any]:
    """Public functional form of the stateless V2 executor."""
    return UniversalExecutor().execute(
        assignment=assignment, provider=provider, event=event,
        evidence_root=evidence_root, max_iterations=max_iterations,
    )


__all__ = [
    "UNIVERSAL_RUN_NEW_RUNTIME",
    "UniversalRunExecutionError",
    "UniversalExecutor",
    "execute_universal_run_node",
]
