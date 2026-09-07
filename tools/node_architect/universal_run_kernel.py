"""Universal Run Kernel v1 vertical slice: immutable records + lifecycle semantics.

This module is intentionally pure and transport-neutral. It does not execute effects,
grant authority, persist state, or mutate external targets. It provides the E1/E2
semantic primitives that later RuntimePlan/RunStateStore adapters can consume.
"""
from __future__ import annotations

import copy
import hashlib
from typing import Any, Mapping

from tools.node_architect.canonical_digest.reference_canonicalizer import canonical_json_bytes

UNIVERSAL_PROFILE_ID = "gwc.universal-run"
UNIVERSAL_PROFILE_VERSION = 1
UNIVERSAL_PROFILE = {"id": UNIVERSAL_PROFILE_ID, "version": UNIVERSAL_PROFILE_VERSION}

GATES = ("G0", "G1", "G2", "G3", "G4", "G5", "G6")
GATE_STATES = {"NOT_STARTED", "ACTIVE", "WAITING", "BLOCKED", "PASSED", "FAILED"}
TERMINAL_STATES = {"OPEN", "ACCEPTED", "FAILED", "CANCELLED", "SUPERSEDED"}
G4_EXPLICIT_OUTCOMES = {"INTEGRATED", "IN_PLACE", "NO_TRANSFER_REQUIRED", "DOMAIN_DEFINED"}

_REQUIRED_RECORD_FIELDS = (
    "record_id",
    "schema_id",
    "schema_version",
    "run_id",
    "created_at",
    "created_by",
    "provenance",
)


class UniversalRunKernelError(ValueError):
    """Deterministic fail-closed kernel error."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code if not detail else f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _require(condition: bool, code: str, detail: str = "") -> None:
    if not condition:
        raise UniversalRunKernelError(code, detail)


def _normalize_profile(profile: Mapping[str, Any] | str) -> dict[str, Any]:
    if isinstance(profile, str):
        if "/" not in profile:
            raise UniversalRunKernelError("LIFECYCLE_PROFILE_UNSUPPORTED", profile)
        profile_id, raw_version = profile.rsplit("/", 1)
        try:
            version = int(raw_version)
        except ValueError as exc:
            raise UniversalRunKernelError("LIFECYCLE_PROFILE_UNSUPPORTED", profile) from exc
        normalized = {"id": profile_id, "version": version}
    elif isinstance(profile, Mapping):
        normalized = {"id": profile.get("id"), "version": profile.get("version")}
    else:
        raise UniversalRunKernelError("LIFECYCLE_PROFILE_UNSUPPORTED")

    if normalized != UNIVERSAL_PROFILE:
        raise UniversalRunKernelError(
            "LIFECYCLE_PROFILE_UNSUPPORTED",
            f"expected {UNIVERSAL_PROFILE_ID}/{UNIVERSAL_PROFILE_VERSION}",
        )
    return dict(UNIVERSAL_PROFILE)


def _canonical_json_bytes(value: Any) -> bytes:
    """Use the repository's existing canonical JSON implementation."""
    return canonical_json_bytes(value)


def _record_digest_subject(record: Mapping[str, Any]) -> dict[str, Any]:
    subject = copy.deepcopy(dict(record))
    subject.pop("content_digest", None)
    return subject


def _validate_record_shape(record: Mapping[str, Any]) -> None:
    for field in _REQUIRED_RECORD_FIELDS:
        _require(field in record, "RECORD_ENVELOPE_INVALID", f"missing {field}")
    for field in ("record_id", "schema_id", "run_id", "created_at"):
        _require(isinstance(record[field], str) and bool(record[field]), "RECORD_ENVELOPE_INVALID", field)
    _require(isinstance(record["schema_version"], (str, int)), "RECORD_ENVELOPE_INVALID", "schema_version")
    _require(isinstance(record["created_by"], Mapping), "RECORD_ENVELOPE_INVALID", "created_by")
    provenance = record["provenance"]
    _require(isinstance(provenance, Mapping), "RECORD_ENVELOPE_INVALID", "provenance")
    for key in ("predecessor_refs", "source_refs"):
        _require(isinstance(provenance.get(key), list), "RECORD_ENVELOPE_INVALID", f"provenance.{key}")
    if "lifecycle_profile" in record:
        _normalize_profile(record["lifecycle_profile"])


def seal_immutable_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return a sealed copy with SHA-256 over canonical bytes excluding content_digest.

    `content_digest` is deliberately outside the digest subject to avoid a circular
    hash. Logical fields remain flat; no payload wrapper is introduced.
    """
    _require("content_digest" not in record, "RECORD_ALREADY_SEALED")
    sealed = copy.deepcopy(dict(record))
    _validate_record_shape(sealed)
    canonical = _canonical_json_bytes(_record_digest_subject(sealed))
    sealed["content_digest"] = {
        "algorithm": "sha256",
        "canonicalization": "JCS",
        "value": hashlib.sha256(canonical).hexdigest(),
    }
    return sealed


def verify_record_digest(record: Mapping[str, Any]) -> bool:
    digest = record.get("content_digest")
    if not isinstance(digest, Mapping):
        return False
    if digest.get("algorithm") != "sha256" or digest.get("canonicalization") != "JCS":
        return False
    value = digest.get("value")
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        _validate_record_shape(record)
        actual = hashlib.sha256(_canonical_json_bytes(_record_digest_subject(record))).hexdigest()
    except (UniversalRunKernelError, TypeError, ValueError):
        return False
    return actual == value


def make_successor_record(
    previous_record: Mapping[str, Any],
    *,
    record_id: str,
    created_at: str,
    created_by: Mapping[str, Any],
    changes: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a successor without mutating historical state.

    Run identity is immutable. The predecessor record must already be valid and the
    successor receives explicit lineage via provenance.predecessor_refs.
    """
    _require(verify_record_digest(previous_record), "PREDECESSOR_RECORD_INVALID")
    _require(record_id != previous_record.get("record_id"), "RECORD_ID_REUSED")
    changes = dict(changes or {})
    if "run_id" in changes and changes["run_id"] != previous_record.get("run_id"):
        raise UniversalRunKernelError("RUN_ID_IMMUTABLE")
    for protected in ("record_id", "created_at", "created_by", "content_digest", "provenance"):
        if protected in changes:
            raise UniversalRunKernelError("IMMUTABLE_ENVELOPE_FIELD_OVERRIDE", protected)

    successor = _record_digest_subject(previous_record)
    successor.update(copy.deepcopy(changes))
    successor["record_id"] = record_id
    successor["created_at"] = created_at
    successor["created_by"] = copy.deepcopy(dict(created_by))

    provenance = copy.deepcopy(dict(successor.get("provenance", {})))
    predecessors = list(provenance.get("predecessor_refs", []))
    previous_id = str(previous_record["record_id"])
    if previous_id not in predecessors:
        predecessors.append(previous_id)
    provenance["predecessor_refs"] = predecessors
    provenance["source_refs"] = list(provenance.get("source_refs", []))
    successor["provenance"] = provenance
    return seal_immutable_record(successor)


def initial_run_state(lifecycle_profile: Mapping[str, Any] | str) -> dict[str, Any]:
    profile = _normalize_profile(lifecycle_profile)
    return {
        "lifecycle_profile": profile,
        "gate_states": {gate: ("ACTIVE" if gate == "G0" else "NOT_STARTED") for gate in GATES},
        "terminal_state": "OPEN",
    }


def _validate_gate_and_state(gate: str, state: str) -> None:
    _require(gate in GATES, "LIFECYCLE_GATE_UNKNOWN", gate)
    _require(state in GATE_STATES, "LIFECYCLE_STATE_UNKNOWN", state)


def transition_lifecycle(
    *,
    lifecycle_profile: Mapping[str, Any] | str,
    current_gate: str,
    current_state: str,
    action: str,
    target_gate: str | None = None,
    explicit_outcome: str | None = None,
) -> dict[str, Any]:
    """Evaluate one legal lifecycle edge; no external state is mutated."""
    profile = _normalize_profile(lifecycle_profile)
    _validate_gate_and_state(current_gate, current_state)
    action = str(action).upper()

    next_gate = current_gate
    next_state = current_state
    edge_kind = "SAME_GATE"

    if action == "ADVANCE":
        _require(current_state == "PASSED", "LIFECYCLE_EDGE_UNDECLARED", "advance requires PASSED")
        idx = GATES.index(current_gate)
        _require(idx < len(GATES) - 1, "LIFECYCLE_EDGE_UNDECLARED", "G6 has no forward gate")
        expected = GATES[idx + 1]
        _require(target_gate == expected, "LIFECYCLE_EDGE_UNDECLARED", f"expected {expected}")
        next_gate, next_state, edge_kind = expected, "ACTIVE", "FORWARD"
    elif action == "WAIT":
        _require(current_state == "ACTIVE", "LIFECYCLE_EDGE_UNDECLARED", "WAIT requires ACTIVE")
        next_state = "WAITING"
    elif action == "CONTINUE":
        _require(current_state in {"WAITING", "BLOCKED"}, "LIFECYCLE_EDGE_UNDECLARED", "CONTINUE requires WAITING/BLOCKED")
        next_state = "ACTIVE"
    elif action in {"RETRY", "RERUN", "REPAIR"}:
        _require(current_state in {"WAITING", "BLOCKED", "FAILED"}, "LIFECYCLE_EDGE_UNDECLARED", action)
        next_state = "ACTIVE"
        edge_kind = "NON_FORWARD"
    elif action == "REPLAN":
        _require(current_gate != "G0", "LIFECYCLE_EDGE_UNDECLARED", "cannot replan before G1")
        next_gate, next_state, edge_kind = "G1", "ACTIVE", "NON_FORWARD"
    elif action == "COMPLETE":
        _require(current_state == "ACTIVE", "LIFECYCLE_EDGE_UNDECLARED", "COMPLETE requires ACTIVE")
        if current_gate == "G4":
            _require(explicit_outcome is not None, "G4_OUTCOME_REQUIRED")
            _require(explicit_outcome in G4_EXPLICIT_OUTCOMES, "G4_OUTCOME_INVALID", str(explicit_outcome))
        next_state = "PASSED"
    elif action == "FAIL":
        next_state, edge_kind = "FAILED", "NON_FORWARD"
    elif action == "CANCEL":
        edge_kind = "NON_FORWARD"
    else:
        raise UniversalRunKernelError("LIFECYCLE_ACTION_UNKNOWN", action)

    if target_gate is not None and action != "ADVANCE":
        _require(target_gate == next_gate, "LIFECYCLE_EDGE_UNDECLARED", "target gate mismatch")

    return {
        "schema_version": "1.0",
        "artifact_type": "universal-lifecycle-transition",
        "lifecycle_profile": profile,
        "current_gate": current_gate,
        "current_state": current_state,
        "action": action,
        "edge_kind": edge_kind,
        "next_gate": next_gate,
        "next_state": next_state,
        "explicit_outcome": explicit_outcome,
        "execution_performed": False,
    }


def derive_terminal_state(
    gate_states: Mapping[str, str],
    *,
    closure_outcome: str | None = None,
    handoff_present: bool = False,
) -> str:
    """Derive terminal state from closure intent and lifecycle evidence."""
    for gate in GATES:
        _validate_gate_and_state(gate, str(gate_states.get(gate, "")))

    if closure_outcome is None or closure_outcome == "OPEN":
        return "OPEN"
    outcome = str(closure_outcome).upper()
    _require(outcome in TERMINAL_STATES - {"OPEN"}, "RUN_TERMINAL_STATE_UNKNOWN", outcome)

    if outcome == "ACCEPTED":
        _require(gate_states.get("G6") == "PASSED", "G6_NOT_PASSED")
        _require(handoff_present, "HANDOFF_REQUIRED")
    return outcome
