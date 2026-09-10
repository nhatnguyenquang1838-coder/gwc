"""Universal Run R1 logical state primitives.

This module composes the existing immutable E1/E2/E3 record semantics into a
transport-neutral logical RunStateStore. It does not execute RuntimePlans,
perform effects, grant authority, or implement Target/Closure/Handoff semantics.
"""
from __future__ import annotations

import copy
import re
from typing import Any, Mapping

from tools.node_architect.universal_run_kernel import (
    GATES,
    GATE_STATES,
    TERMINAL_STATES,
    UNIVERSAL_PROFILE,
    UniversalRunKernelError,
    seal_immutable_record,
    verify_record_digest,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FUTURE_REF_KEYS = ("target_contract_ref", "closure_receipt_ref", "handoff_receipt_ref")
_EXECUTION_REF_KEYS = ("runtime_plan_ref", "runtime_plan_digest", "cursor_ref")


def _require(condition: bool, code: str, detail: str = "") -> None:
    if not condition:
        raise UniversalRunKernelError(code, detail)


def _text(value: Any, field: str) -> str:
    _require(isinstance(value, str) and bool(value) and value == value.strip(), "RUN_STATE_INVALID", field)
    _require("\r" not in value and "\n" not in value, "RUN_STATE_INVALID", field)
    return value


def _digest(value: Any, field: str) -> str:
    value = _text(value, field)
    _require(bool(_SHA256_RE.fullmatch(value)), "RUN_STATE_DIGEST_INVALID", field)
    return value


def _integer(value: Any, field: str, minimum: int) -> int:
    _require(isinstance(value, int) and not isinstance(value, bool) and value >= minimum, "RUN_STATE_INVALID", field)
    return value


def _normalize_execution_refs(value: Any) -> dict[str, str | None]:
    _require(isinstance(value, Mapping), "RUN_STATE_EXECUTION_REFS_INVALID")
    result: dict[str, str | None] = {}
    for key in _EXECUTION_REF_KEYS:
        item = value.get(key)
        if item is None:
            result[key] = None
        elif key == "runtime_plan_digest":
            result[key] = _digest(item, f"execution_refs.{key}")
        else:
            result[key] = _text(item, f"execution_refs.{key}")
    return result


def _normalize_future_refs(value: Any) -> dict[str, str | None]:
    _require(isinstance(value, Mapping), "RUN_STATE_FUTURE_REFS_INVALID")
    result: dict[str, str | None] = {}
    for key in _FUTURE_REF_KEYS:
        item = value.get(key)
        result[key] = None if item is None else _text(item, f"future_contract_refs.{key}")
    return result


def _validate_gate_projection(active_gate: Any, gate_states: Any) -> tuple[str, dict[str, str]]:
    active_gate = _text(active_gate, "active_gate")
    _require(active_gate in GATES, "LIFECYCLE_GATE_UNKNOWN", active_gate)
    _require(isinstance(gate_states, Mapping), "RUN_STATE_GATE_STATES_INVALID")
    _require(set(gate_states.keys()) == set(GATES), "RUN_STATE_GATE_POSITIONS_INVALID")
    normalized: dict[str, str] = {}
    for gate in GATES:
        state = gate_states.get(gate)
        _require(isinstance(state, str) and state in GATE_STATES, "LIFECYCLE_STATE_UNKNOWN", f"{gate}:{state}")
        normalized[gate] = state
    _require(normalized[active_gate] != "NOT_STARTED", "RUN_STATE_ACTIVE_GATE_INVALID", active_gate)
    return active_gate, normalized


def _validate_provenance(value: Any) -> dict[str, list[str]]:
    _require(isinstance(value, Mapping), "RUN_STATE_PROVENANCE_INVALID")
    result: dict[str, list[str]] = {}
    for key in ("predecessor_refs", "source_refs"):
        items = value.get(key)
        _require(isinstance(items, list), "RUN_STATE_PROVENANCE_INVALID", key)
        result[key] = [_text(item, f"provenance.{key}") for item in items]
    return result


def _validate_state_payload(record: Mapping[str, Any]) -> None:
    _text(record.get("record_id"), "record_id")
    _text(record.get("run_id"), "run_id")
    _require(record.get("lifecycle_profile") == UNIVERSAL_PROFILE, "LIFECYCLE_PROFILE_UNSUPPORTED")
    _text(record.get("run_manifest_ref"), "run_manifest_ref")
    _digest(record.get("run_manifest_digest"), "run_manifest_digest")
    state_revision = _integer(record.get("state_revision"), "state_revision", 1)
    _integer(record.get("sequence"), "sequence", 0)

    predecessor_ref = record.get("predecessor_state_ref")
    predecessor_digest = record.get("predecessor_state_digest")
    if state_revision == 1:
        _require(
            predecessor_ref is None and predecessor_digest is None,
            "RUN_STATE_GENESIS_PREDECESSOR_FORBIDDEN",
        )
    else:
        _require(
            predecessor_ref is not None and predecessor_digest is not None,
            "RUN_STATE_PREDECESSOR_REQUIRED",
        )
        _text(predecessor_ref, "predecessor_state_ref")
        _digest(predecessor_digest, "predecessor_state_digest")

    active_gate, gate_states = _validate_gate_projection(record.get("active_gate"), record.get("gate_states"))
    terminal_state = str(record.get("terminal_state", "")).upper()
    _require(terminal_state in TERMINAL_STATES, "RUN_TERMINAL_STATE_UNKNOWN", terminal_state)
    # R1 has no Closure/HandoffReceipt semantics. Presence of future opaque refs
    # must never be interpreted as acceptance.
    _require(terminal_state != "ACCEPTED", "R1_ACCEPTED_REQUIRES_HANDOFF_SEMANTICS")

    _normalize_execution_refs(record.get("execution_refs"))
    _normalize_future_refs(record.get("future_contract_refs"))
    _validate_provenance(record.get("provenance"))

    run_manifest_run_id = record.get("run_manifest_run_id")
    parent_run_ref = record.get("parent_run_ref")
    child_run_ref = record.get("child_run_ref")
    if parent_run_ref is not None or child_run_ref is not None:
        _require(run_manifest_run_id is not None, "CHILD_STATE_MANIFEST_RUN_ID_REQUIRED")
        _require(parent_run_ref is not None and child_run_ref is not None, "CHILD_STATE_LINEAGE_INCOMPLETE")
    if run_manifest_run_id is not None:
        _require(_text(run_manifest_run_id, "run_manifest_run_id") == record["run_id"], "RUN_MANIFEST_RUN_ID_MISMATCH")
    if parent_run_ref is not None or child_run_ref is not None:
        parent_run_ref = _text(parent_run_ref, "parent_run_ref")
        child_run_ref = _text(child_run_ref, "child_run_ref")
        _require(child_run_ref == record["run_id"], "CHILD_STATE_RUN_ID_MISMATCH")
        _require(parent_run_ref == record["run_manifest_ref"], "CHILD_STATE_PARENT_MANIFEST_MISMATCH")

    # Avoid accidental authority introduction through an R1 state projection.
    _require(record.get("authority_granted", False) is False, "R1_AUTHORITY_FIELD_FORBIDDEN")
    _ = active_gate, gate_states


def create_run_state_record(
    *,
    record_id: str,
    run_id: str,
    lifecycle_profile: Mapping[str, Any] | str,
    run_manifest_ref: str,
    run_manifest_digest: str,
    state_revision: int,
    predecessor_state_ref: str | None,
    predecessor_state_digest: str | None,
    sequence: int,
    active_gate: str,
    gate_states: Mapping[str, str],
    terminal_state: str,
    execution_refs: Mapping[str, Any],
    future_contract_refs: Mapping[str, Any],
    created_at: str,
    created_by: Mapping[str, Any],
    provenance: Mapping[str, Any],
    run_manifest_run_id: str | None = None,
    parent_run_ref: str | None = None,
    child_run_ref: str | None = None,
) -> dict[str, Any]:
    """Create a sealed immutable RunStateRecord with no effect/authority semantics."""
    record: dict[str, Any] = {
        "record_id": record_id,
        "schema_id": "gwc.universal-run.run-state-record",
        "schema_version": 1,
        "run_id": run_id,
        "created_at": created_at,
        "created_by": copy.deepcopy(dict(created_by)),
        "lifecycle_profile": copy.deepcopy(lifecycle_profile),
        "provenance": _validate_provenance(provenance),
        "run_manifest_ref": run_manifest_ref,
        "run_manifest_digest": run_manifest_digest,
        "state_revision": state_revision,
        "predecessor_state_ref": predecessor_state_ref,
        "predecessor_state_digest": predecessor_state_digest,
        "sequence": sequence,
        "active_gate": active_gate,
        "gate_states": copy.deepcopy(dict(gate_states)),
        "terminal_state": str(terminal_state).upper(),
        "execution_refs": _normalize_execution_refs(execution_refs),
        "future_contract_refs": _normalize_future_refs(future_contract_refs),
    }
    if run_manifest_run_id is not None:
        record["run_manifest_run_id"] = run_manifest_run_id
    if parent_run_ref is not None:
        record["parent_run_ref"] = parent_run_ref
    if child_run_ref is not None:
        record["child_run_ref"] = child_run_ref
    _validate_state_payload(record)
    return seal_immutable_record(record)


def verify_run_state_record(record: Mapping[str, Any]) -> bool:
    if not isinstance(record, Mapping) or record.get("schema_id") != "gwc.universal-run.run-state-record":
        return False
    if not verify_record_digest(record):
        return False
    try:
        _validate_state_payload(record)
    except (UniversalRunKernelError, TypeError, ValueError):
        return False
    return True


def make_successor_state_record(
    previous: Mapping[str, Any],
    *,
    record_id: str,
    created_at: str,
    created_by: Mapping[str, Any],
    changes: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create an immutable successor bound exactly to predecessor digest/sequence."""
    _require(verify_run_state_record(previous), "PREDECESSOR_RUN_STATE_INVALID")
    delta = dict(changes or {})
    if "run_id" in delta:
        _require(delta["run_id"] == previous["run_id"], "RUN_ID_IMMUTABLE")
    if "predecessor_state_digest" in delta:
        _require(
            delta["predecessor_state_digest"] == previous["content_digest"]["value"],
            "RUN_STATE_PREDECESSOR_DIGEST_MISMATCH",
        )
    if "predecessor_state_ref" in delta:
        _require(delta["predecessor_state_ref"] == previous["record_id"], "RUN_STATE_PREDECESSOR_REF_MISMATCH")

    expected_sequence = int(previous["sequence"]) + 1
    expected_revision = int(previous["state_revision"]) + 1
    _require(delta.get("sequence", expected_sequence) == expected_sequence, "RUN_STATE_SEQUENCE_STALE")
    _require(delta.get("state_revision", expected_revision) == expected_revision, "RUN_STATE_REVISION_STALE")

    protected = {"record_id", "schema_id", "schema_version", "created_at", "created_by", "content_digest", "provenance"}
    for field in protected:
        _require(field not in delta, "IMMUTABLE_ENVELOPE_FIELD_OVERRIDE", field)

    successor = copy.deepcopy(dict(previous))
    successor.pop("content_digest", None)
    successor.update(copy.deepcopy(delta))
    successor["record_id"] = record_id
    successor["created_at"] = created_at
    successor["created_by"] = copy.deepcopy(dict(created_by))
    successor["run_id"] = previous["run_id"]
    successor["sequence"] = expected_sequence
    successor["state_revision"] = expected_revision
    successor["predecessor_state_ref"] = previous["record_id"]
    successor["predecessor_state_digest"] = previous["content_digest"]["value"]
    provenance = copy.deepcopy(dict(previous["provenance"]))
    predecessors = list(provenance.get("predecessor_refs", []))
    if previous["record_id"] not in predecessors:
        predecessors.append(previous["record_id"])
    provenance["predecessor_refs"] = predecessors
    provenance["source_refs"] = list(provenance.get("source_refs", []))
    successor["provenance"] = provenance
    _validate_state_payload(successor)
    return seal_immutable_record(successor)


# Compatibility spelling accepted by the RED contract helper.
make_successor_run_state_record = make_successor_state_record


class LogicalRunStateStore:
    """In-memory logical CAS store for one Run; performs no external effects."""

    def __init__(self) -> None:
        self._bound_run_id: str | None = None
        self._latest: dict[str, dict[str, Any]] = {}
        self._history: dict[str, list[dict[str, Any]]] = {}
        self.executed_effects: list[Any] = []

    def put(self, record: Mapping[str, Any], *, expected_predecessor_digest: str | None) -> dict[str, Any]:
        _require(verify_run_state_record(record), "RUN_STATE_RECORD_INVALID")
        run_id = str(record["run_id"])
        if self._bound_run_id is not None:
            _require(run_id == self._bound_run_id, "RUN_STATE_STORE_CROSS_RUN_WRITE")

        current = self._latest.get(run_id)
        if current is None:
            _require(expected_predecessor_digest is None, "RUN_STATE_STORE_EXPECTED_PREDECESSOR_MISMATCH")
            _require(record["state_revision"] == 1, "RUN_STATE_STORE_FIRST_REVISION_INVALID")
            _require(record["sequence"] == 0, "RUN_STATE_STORE_FIRST_SEQUENCE_INVALID")
            _require(record["predecessor_state_ref"] is None and record["predecessor_state_digest"] is None, "RUN_STATE_STORE_FIRST_PREDECESSOR_INVALID")
        else:
            current_digest = current["content_digest"]["value"]
            _require(expected_predecessor_digest == current_digest, "RUN_STATE_STORE_STALE_WRITER")
            _require(record["predecessor_state_ref"] == current["record_id"], "RUN_STATE_STORE_PREDECESSOR_REF_MISMATCH")
            _require(record["predecessor_state_digest"] == current_digest, "RUN_STATE_STORE_PREDECESSOR_DIGEST_MISMATCH")
            _require(record["state_revision"] == current["state_revision"] + 1, "RUN_STATE_STORE_REVISION_STALE")
            _require(record["sequence"] == current["sequence"] + 1, "RUN_STATE_STORE_SEQUENCE_STALE")

        if self._bound_run_id is None:
            self._bound_run_id = run_id
        stored = copy.deepcopy(dict(record))
        self._history.setdefault(run_id, []).append(stored)
        self._latest[run_id] = stored
        return copy.deepcopy(stored)

    def get(self, run_id: str) -> dict[str, Any] | None:
        current = self._latest.get(run_id)
        return None if current is None else copy.deepcopy(current)

    def history(self, run_id: str) -> tuple[dict[str, Any], ...]:
        return tuple(copy.deepcopy(item) for item in self._history.get(run_id, []))


__all__ = [
    "LogicalRunStateStore",
    "create_run_state_record",
    "make_successor_state_record",
    "make_successor_run_state_record",
    "verify_run_state_record",
]
