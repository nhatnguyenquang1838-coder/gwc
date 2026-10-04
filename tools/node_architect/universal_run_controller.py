"""Native Universal Runtime v2 Controller.

The Controller owns the plan/state cursor and actor assignment. It has no
mailbox, history-controller, or transport dependency; adapters receive decisions
only after this native state has been validated.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from .q0_qualification import (
    GATE_EVIDENCE,
    Q0_ACTIONS,
    advance_qualification_gate,
    complete_q0_gate,
    q0_qualification_profile,
)
from .universal_run_kernel import GATES, UNIVERSAL_PROFILE
from .universal_run_topology import validate_node_allocation
from .universal_runtime_profile import load_universal_v2_default_profile


class UniversalControllerError(ValueError):
    """A malformed or misbound native V2 control record."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _digest(value: Mapping[str, Any], digest_field: str) -> str:
    subject = {key: item for key, item in value.items() if key != digest_field}
    return "sha256:" + hashlib.sha256(_canonical_bytes(subject)).hexdigest()


def _require(condition: bool, code: str, detail: str = "") -> None:
    if not condition:
        raise UniversalControllerError(code, detail)


def materialize_controller_transition_receipt(
    *, receipt: Mapping[str, Any], path: str | Path
) -> dict[str, Any]:
    """Persist one immutable Controller transition receipt with exact readback."""
    _require(isinstance(receipt, Mapping), "CONTROLLER_TRANSITION_RECEIPT_INVALID")
    _require(
        isinstance(receipt.get("successor_snapshot_ref"), str)
        and bool(receipt.get("successor_snapshot_ref"))
        and isinstance(receipt.get("successor_snapshot_file_sha256"), str)
        and isinstance(receipt.get("successor_snapshot_digest"), str)
        and isinstance(receipt.get("successor_state_digest"), str),
        "CONTROLLER_SUCCESSOR_SNAPSHOT_REQUIRED",
    )
    schema_path = Path(__file__).resolve().parents[2] / "schemas/node-architect/universal-run/controller-transition-receipt.schema.json"
    try:
        import jsonschema
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.validate(dict(receipt), schema)
    except Exception as exc:
        raise UniversalControllerError("CONTROLLER_TRANSITION_RECEIPT_INVALID", str(exc)) from exc
    _require(receipt.get("transition_digest") == _digest(receipt, "transition_digest"), "CONTROLLER_TRANSITION_DIGEST_INVALID")
    target = Path(path)
    _require(not target.is_symlink(), "CONTROLLER_TRANSITION_RECEIPT_PATH_SYMLINK")
    payload = (json.dumps(dict(receipt), sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
    if target.exists():
        _require(target.read_bytes() == payload, "CONTROLLER_TRANSITION_RECEIPT_CONFLICT")
    snapshot_path = Path(str(receipt["successor_snapshot_ref"]))
    try:
        snapshot_bytes = snapshot_path.read_bytes()
        snapshot = json.loads(snapshot_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise UniversalControllerError("CONTROLLER_SUCCESSOR_SNAPSHOT_READBACK_FAILED", str(exc)) from exc
    _require(hashlib.sha256(snapshot_bytes).hexdigest() == receipt["successor_snapshot_file_sha256"], "CONTROLLER_SUCCESSOR_SNAPSHOT_FILE_HASH_MISMATCH")
    _require(isinstance(snapshot, Mapping) and snapshot.get("snapshot_digest") == _digest(snapshot, "snapshot_digest"), "CONTROLLER_SUCCESSOR_SNAPSHOT_DIGEST_INVALID")
    snapshot_state = snapshot.get("successor_run_state")
    post_state = receipt.get("post_state")
    _require(
        isinstance(snapshot_state, Mapping)
        and snapshot_state.get("state_digest") == _digest(snapshot_state, "state_digest")
        and snapshot.get("snapshot_digest") == receipt["successor_snapshot_digest"]
        and snapshot_state.get("state_digest") == receipt["successor_state_digest"]
        and isinstance(post_state, Mapping)
        and post_state.get("sequence") == snapshot_state.get("sequence")
        and post_state.get("state_digest") == snapshot_state.get("state_digest")
        and snapshot.get("run_id") == receipt.get("run_id")
        and snapshot.get("runtime_plan_digest") == receipt.get("runtime_plan_digest")
        and snapshot.get("transition_ref") == receipt.get("transition_ref"),
        "CONTROLLER_SUCCESSOR_SNAPSHOT_BINDING_MISMATCH",
    )
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        _require(not target.is_symlink(), "CONTROLLER_TRANSITION_RECEIPT_PATH_SYMLINK")
        try:
            existing = target.read_bytes()
        except OSError as exc:
            raise UniversalControllerError("CONTROLLER_TRANSITION_RECEIPT_READBACK_FAILED", str(exc)) from exc
        _require(existing == payload, "CONTROLLER_TRANSITION_RECEIPT_CONFLICT")
        idempotent_replay = True
    except OSError as exc:
        raise UniversalControllerError("CONTROLLER_TRANSITION_RECEIPT_WRITE_FAILED", str(exc)) from exc
    else:
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as exc:
            raise UniversalControllerError("CONTROLLER_TRANSITION_RECEIPT_WRITE_FAILED", str(exc)) from exc
        idempotent_replay = False
    try:
        readback = target.read_bytes()
        decoded = json.loads(readback)
    except (OSError, json.JSONDecodeError) as exc:
        raise UniversalControllerError("CONTROLLER_TRANSITION_RECEIPT_READBACK_FAILED", str(exc)) from exc
    _require(readback == payload and decoded == dict(receipt), "CONTROLLER_TRANSITION_RECEIPT_READBACK_MISMATCH")
    _require(decoded.get("transition_digest") == _digest(decoded, "transition_digest"), "CONTROLLER_TRANSITION_DIGEST_INVALID")
    return {
        "path": str(target),
        "file_sha256": hashlib.sha256(readback).hexdigest(),
        "transition_digest": decoded["transition_digest"],
        "idempotent_replay": idempotent_replay,
    }


class UniversalController:
    """Validated in-process controller for a single native Universal Run cursor."""

    def __init__(
        self,
        *,
        profile: Mapping[str, Any],
        runtime_plan: Mapping[str, Any],
        run_state: Mapping[str, Any],
        node_allocation: Mapping[str, Any],
    ) -> None:
        canonical_profile = load_universal_v2_default_profile()
        _require(dict(profile) == canonical_profile, "RUNTIME_PROFILE_BINDING_MISMATCH")
        _require(runtime_plan.get("schema_id") == "gwc.universal-run.runtime-plan.v2", "RUNTIME_PLAN_SCHEMA_MISMATCH")
        _require(runtime_plan.get("schema_version") == 2, "RUNTIME_PLAN_SCHEMA_MISMATCH")
        _require(runtime_plan.get("digest") == _digest(runtime_plan, "digest"), "RUNTIME_PLAN_DIGEST_INVALID")
        _require(runtime_plan.get("runtime_epoch") == canonical_profile["runtime_epoch"], "RUNTIME_EPOCH_MISMATCH")
        _require(
            runtime_plan.get("runtime_default_profile_digest") == canonical_profile["profile_digest"],
            "RUNTIME_PROFILE_BINDING_MISMATCH",
        )
        q0_profile = q0_qualification_profile()
        _require(
            runtime_plan.get("qualification_profile_digest") == q0_profile["profile_digest"],
            "QUALIFICATION_PROFILE_BINDING_MISMATCH",
        )
        _require(run_state.get("schema_id") == "gwc.universal-run.run-state.v2", "RUN_STATE_SCHEMA_MISMATCH")
        _require(run_state.get("schema_version") == 2, "RUN_STATE_SCHEMA_MISMATCH")
        _require(run_state.get("state_digest") == _digest(run_state, "state_digest"), "RUN_STATE_DIGEST_INVALID")
        _require(run_state.get("run_id") == runtime_plan.get("run_id"), "RUN_ID_MISMATCH")
        _require(run_state.get("runtime_epoch") == canonical_profile["runtime_epoch"], "RUNTIME_EPOCH_MISMATCH")
        gate = run_state.get("active_gate")
        _require(gate in GATES and gate in Q0_ACTIONS, "UNIVERSAL_GATE_UNKNOWN", str(gate))
        _require(isinstance(run_state.get("sequence"), int) and run_state["sequence"] >= 1, "RUN_STATE_SEQUENCE_INVALID")
        validate_node_allocation(node_allocation)
        execution_refs = run_state.get("execution_refs")
        _require(isinstance(execution_refs, Mapping), "RUN_STATE_EXECUTION_REFS_INVALID")
        state_plan_digest = run_state.get("runtime_plan_digest", execution_refs.get("runtime_plan_digest"))
        _require(state_plan_digest == runtime_plan.get("digest"), "RUN_STATE_PLAN_BINDING_MISMATCH")
        _require(node_allocation.get("run_id") == run_state.get("run_id"), "NODE_ALLOCATION_RUN_MISMATCH")
        allocation_id = node_allocation.get("node_allocation_id")
        state_allocation_id = run_state.get("node_allocation_id", execution_refs.get("node_allocation_id"))
        _require(allocation_id == state_allocation_id, "NODE_ALLOCATION_BINDING_MISMATCH")
        _require(allocation_id in runtime_plan.get("node_allocations", []), "NODE_ALLOCATION_NOT_IN_PLAN")
        allocation_ref = str(run_state.get("node_allocation_ref", execution_refs.get("node_allocation_ref", "")))
        referenced_record_id = allocation_ref.rsplit("#record_id=", 1)[-1]
        _require(referenced_record_id == node_allocation.get("record_id"), "NODE_ALLOCATION_REF_MISMATCH")
        _require(
            execution_refs.get("runtime_plan_digest") == runtime_plan.get("digest"),
            "RUN_STATE_PLAN_BINDING_MISMATCH",
        )
        _require(
            execution_refs.get("qualification_profile_digest") == q0_profile["profile_digest"],
            "QUALIFICATION_PROFILE_BINDING_MISMATCH",
        )
        _require(
            execution_refs.get("branch") == runtime_plan.get("source_binding", {}).get("branch"),
            "RUN_STATE_BRANCH_BINDING_MISMATCH",
        )
        source_binding = runtime_plan.get("source_binding")
        _require(isinstance(source_binding, Mapping), "RUNTIME_PLAN_SOURCE_BINDING_INVALID")
        _require(
            execution_refs.get("candidate_sha") == source_binding.get("pre_head_sha"),
            "RUN_STATE_HEAD_BINDING_MISMATCH",
        )

        self.profile = dict(canonical_profile)
        self.runtime_plan = dict(runtime_plan)
        self.run_state = dict(run_state)
        self.node_allocation = dict(node_allocation)
        self._assignment: dict[str, Any] | None = None

    @classmethod
    def from_manifest(cls, *, profile: Mapping[str, Any], manifest: Mapping[str, Any]) -> "UniversalController":
        required = ("runtime_plan", "run_state", "node_allocation")
        missing = [key for key in required if not isinstance(manifest.get(key), Mapping)]
        _require(not missing, "UNIVERSAL_V2_MANIFEST_BINDING_INVALID", ",".join(missing))
        return cls(
            profile=profile,
            runtime_plan=manifest["runtime_plan"],
            run_state=manifest["run_state"],
            node_allocation=manifest["node_allocation"],
        )

    def assign_current_action(self) -> dict[str, Any]:
        """Return one typed action owned by the current native RunState actor."""
        gate = str(self.run_state["active_gate"])
        action = Q0_ACTIONS[gate]
        owner = self.run_state.get("next_owner")
        _require(owner in {"EXECUTOR", "CONTROLLER"}, "RUN_STATE_NEXT_OWNER_INVALID", str(owner))
        execution_refs = self.run_state["execution_refs"]
        source_binding = self.runtime_plan["source_binding"]
        identity = {
            "run_id": self.run_state["run_id"],
            "sequence": self.run_state["sequence"],
            "runtime_plan_digest": self.runtime_plan["digest"],
            "node_allocation_id": self.node_allocation["node_allocation_id"],
            "gate": gate,
            "action": action,
        }
        if owner == "CONTROLLER":
            typed_next = self.run_state.get("typed_next")
            _require(isinstance(typed_next, str) and bool(typed_next), "RUN_STATE_CONTROLLER_TYPED_NEXT_REQUIRED")
            identity["actor"] = "CONTROLLER"
        idempotency_key = "sha256:" + hashlib.sha256(_canonical_bytes(identity)).hexdigest()
        scope = {
            "repository": source_binding["repository"],
            "branch": source_binding["branch"],
            "base_sha": execution_refs.get("base_sha"),
            "head_sha": execution_refs.get("candidate_sha"),
            "scope_hash": idempotency_key,
        }
        if owner == "EXECUTOR":
            body = {
                "schema_id": "gwc.universal-run.executor-assignment.v2",
                "schema_version": 2,
                "runtime_protocol": self.profile["runtime_protocol"],
                "runtime_epoch": self.profile["runtime_epoch"],
                "runtime_profile_digest": self.profile["profile_digest"],
                "run_id": self.run_state["run_id"],
                "sequence": self.run_state["sequence"],
                "gate": gate,
                "action": action,
                "actor": "EXECUTOR",
                "node_id": self.node_allocation["provenance"]["source_refs"][0],
                "node_allocation_id": self.node_allocation["node_allocation_id"],
                "node_allocation_digest": self.node_allocation["content_digest"]["value"],
                "runtime_plan_digest": self.runtime_plan["digest"],
                "idempotency_key": idempotency_key,
                "scope": scope,
                "target": {"kind": "candidate-branch", "identity": scope["head_sha"]},
                "authority_decision_ref": None,
                "effect_authority": "NONE",
                "evidence_requirements": list(GATE_EVIDENCE[gate]),
            }
        else:
            body = {
                "schema_id": "gwc.universal-run.controller-local-action.v2",
                "schema_version": 2,
                "runtime_protocol": self.profile["runtime_protocol"],
                "runtime_epoch": self.profile["runtime_epoch"],
                "runtime_profile_digest": self.profile["profile_digest"],
                "run_id": self.run_state["run_id"],
                "sequence": self.run_state["sequence"],
                "gate": gate,
                "action": action,
                "actor": "CONTROLLER",
                "next_owner": "CONTROLLER",
                "typed_next": typed_next,
                "node_id": self.node_allocation["provenance"]["source_refs"][0],
                "node_allocation_id": self.node_allocation["node_allocation_id"],
                "node_allocation_digest": self.node_allocation["content_digest"]["value"],
                "runtime_plan_digest": self.runtime_plan["digest"],
                "idempotency_key": idempotency_key,
                "scope": scope,
                "target": {"kind": "candidate-branch", "identity": scope["head_sha"]},
                "effect_authority": "NONE",
                "evidence_requirements": list(GATE_EVIDENCE[gate]),
                "authority_granted": False,
                "executed_effects": [],
            }
        self._assignment = {**body, "assignment_digest": "sha256:" + hashlib.sha256(_canonical_bytes(body)).hexdigest()}
        return dict(self._assignment)
    def consume_executor_receipt(
        self,
        receipt: Mapping[str, Any],
        *,
        evidence_artifacts: Mapping[str, Any] | None = None,
        transition_receipt_ref: str | None = None,
    ) -> dict[str, Any]:
        """Validate one actor receipt, record exactly-once consumption, and advance the native cursor."""
        _require(isinstance(receipt, Mapping), "EXECUTOR_RECEIPT_INVALID")
        _require(
            not any(key in receipt for key in ("typed_next", "successor_run_state", "controller_decision", "next_gate")),
            "EXECUTOR_CONTROL_FIELD_FORBIDDEN",
        )
        _require(receipt.get("schema_id") == "gwc.universal-run.executor-action-receipt.v2", "EXECUTOR_RECEIPT_SCHEMA_MISMATCH")
        _require(receipt.get("runtime_protocol") == self.profile["runtime_protocol"], "EXECUTOR_RECEIPT_PROTOCOL_MISMATCH")
        _require(receipt.get("runtime_epoch") == self.profile["runtime_epoch"], "EXECUTOR_RECEIPT_EPOCH_MISMATCH")
        _require(receipt.get("actor") == "EXECUTOR", "EXECUTOR_RECEIPT_ACTOR_MISMATCH")
        _require(receipt.get("run_id") == self.run_state["run_id"], "EXECUTOR_RECEIPT_RUN_MISMATCH")
        _require(receipt.get("runtime_plan_digest") == self.runtime_plan["digest"], "EXECUTOR_RECEIPT_PLAN_MISMATCH")
        _require(receipt.get("host_status") == "ACTION_COMPLETE", "EXECUTOR_ACTION_NOT_COMPLETE")
        _require(receipt.get("authority_granted") is False and receipt.get("executed_effects") == [], "EXECUTOR_EFFECT_BOUNDARY_VIOLATION")
        receipt_digest = receipt.get("receipt_digest")
        _require(receipt_digest == _digest(receipt, "receipt_digest"), "EXECUTOR_RECEIPT_DIGEST_INVALID")
        idempotency_key = receipt.get("event_id")
        _require(isinstance(idempotency_key, str) and bool(idempotency_key), "EXECUTOR_RECEIPT_IDEMPOTENCY_KEY_REQUIRED")

        ledger = list(self.run_state.get("receipt_consumption_ledger", []))
        _require(all(isinstance(item, Mapping) for item in ledger), "EXECUTOR_RECEIPT_CONSUMPTION_LEDGER_INVALID")
        prior_matches = [item for item in ledger if item.get("idempotency_key") == idempotency_key]
        _require(len(prior_matches) <= 1, "EXECUTOR_RECEIPT_CONSUMPTION_LEDGER_INVALID")
        prior = prior_matches[0] if prior_matches else None
        if prior is not None:
            _require(prior.get("receipt_digest") == receipt_digest, "EXECUTOR_RECEIPT_IDEMPOTENCY_CONFLICT")
            _require(
                prior.get("run_id") == self.run_state["run_id"]
                and prior.get("runtime_plan_digest") == self.runtime_plan["digest"]
                and prior.get("candidate_sha") == self.run_state["execution_refs"].get("candidate_sha")
                and prior.get("idempotency_key") == idempotency_key
                and prior.get("assignment_digest") == receipt.get("assignment_digest")
                and prior.get("sequence") == receipt.get("sequence")
                and prior.get("gate") == receipt.get("gate")
                and prior.get("action") == receipt.get("action"),
                "EXECUTOR_RECEIPT_IDEMPOTENCY_CONFLICT",
            )
            return {
                "schema_id": "gwc.universal-run.controller-decision.v2",
                "runtime_protocol": self.profile["runtime_protocol"],
                "run_id": self.run_state["run_id"],
                "sequence": self.run_state["sequence"],
                "active_gate": self.run_state["active_gate"],
                "from_gate": prior["gate"],
                "next_gate": prior["to_gate"],
                "next_owner": prior["next_owner"],
                "typed_next": prior["typed_next"],
                "gate_advanced": False,
                "idempotent_replay": True,
                "consumed_receipt_digest": receipt_digest,
                "transition_ref": prior["transition_ref"],
                "successor_run_state": copy.deepcopy(self.run_state),
                "authority_granted": False,
                "executed_effects": [],
            }
        consumed = list(self.run_state.get("consumed_receipts", []))
        _require(
            self.run_state.get("next_owner") == "EXECUTOR",
            "CONTROLLER_OWNER_EXECUTOR_RECEIPT_FORBIDDEN",
            str(self.run_state.get("next_owner")),
        )
        _require(receipt_digest not in consumed, "EXECUTOR_RECEIPT_CONSUMPTION_RECORD_MISSING")

        assignment = self._assignment
        _require(isinstance(assignment, Mapping), "EXECUTOR_ASSIGNMENT_NOT_ISSUED")
        _require(assignment.get("actor") == "EXECUTOR", "EXECUTOR_ASSIGNMENT_ACTOR_MISMATCH")
        expected_fields = {
            "run_id": "run_id",
            "sequence": "sequence",
            "gate": "gate",
            "action": "action",
            "node_id": "node_id",
            "node_allocation_id": "node_allocation_id",
            "runtime_plan_digest": "runtime_plan_digest",
            "assignment_digest": "assignment_digest",
            "event_id": "idempotency_key",
        }
        for receipt_field, assignment_field in expected_fields.items():
            _require(receipt.get(receipt_field) == assignment[assignment_field], "EXECUTOR_RECEIPT_BINDING_MISMATCH", receipt_field)
        _require(receipt.get("sequence") == self.run_state["sequence"], "EXECUTOR_RECEIPT_SEQUENCE_MISMATCH")

        gate = str(assignment["gate"])
        if gate == "UR.G2":
            evidence = {"EXECUTION_RECEIPT": dict(receipt)}
        else:
            evidence = copy.deepcopy(dict(evidence_artifacts or {}))
            _require(bool(evidence), "Q0_GATE_EVIDENCE_REQUIRED", gate)
        candidate_sha = str(self.runtime_plan["source_binding"]["pre_head_sha"])
        complete_q0_gate(
            gate=gate,
            evidence=evidence,
            run_id=assignment["run_id"],
            runtime_plan_digest=assignment["runtime_plan_digest"],
            candidate_sha=candidate_sha,
        )
        transition = advance_qualification_gate(
            current_gate=gate,
            current_state="ACTIVE",
            evidence=evidence,
            sequence=int(self.run_state["sequence"]),
            run_id=assignment["run_id"],
            runtime_plan_digest=assignment["runtime_plan_digest"],
            candidate_sha=candidate_sha,
        )
        pre_state = copy.deepcopy(self.run_state)
        successor = copy.deepcopy(self.run_state)
        successor.pop("state_digest", None)
        old_sequence = int(successor["sequence"])
        successor["predecessor_sequence"] = old_sequence
        successor["predecessor_state_digest"] = pre_state["state_digest"]
        successor["sequence"] = old_sequence + int(transition["sequence_delta"])
        successor["active_gate"] = transition["next_gate"]
        successor["gate_evidence"] = copy.deepcopy(evidence)
        successor["evidence_gap"] = list(GATE_EVIDENCE[successor["active_gate"]])
        typed_next = (
            "MATERIALIZE_UR_G3_VERIFICATION_RECEIPT"
            if successor["active_gate"] == "UR.G3"
            else "CONTINUE_UNIVERSAL_LANE_REMEDIATION"
        )
        next_owner = "EXECUTOR" if successor["active_gate"] == "UR.G3" else "CONTROLLER"
        successor["typed_next"] = typed_next
        successor["next_owner"] = next_owner
        successor_consumed = list(successor.get("consumed_receipts", []))
        successor_consumed.append(receipt_digest)
        successor["consumed_receipts"] = successor_consumed
        transition_ref = transition_receipt_ref or (
            f"{successor['run_id']}:controller-transition:seq{old_sequence}-seq{successor['sequence']}:{receipt_digest}"
        )
        ledger_record = {
            "run_id": successor["run_id"],
            "runtime_plan_digest": self.runtime_plan["digest"],
            "candidate_sha": candidate_sha,
            "idempotency_key": idempotency_key,
            "receipt_digest": receipt_digest,
            "assignment_digest": assignment["assignment_digest"],
            "sequence": old_sequence,
            "gate": gate,
            "action": assignment["action"],
            "to_gate": successor["active_gate"],
            "typed_next": typed_next,
            "next_owner": next_owner,
            "transition_ref": transition_ref,
        }
        successor["receipt_consumption_ledger"] = ledger + [ledger_record]
        execution_refs = copy.deepcopy(dict(successor.get("execution_refs", {})))
        execution_refs["cursor_ref"] = f"{successor['run_id']}:{successor['active_gate']}:seq{successor['sequence']}"
        successor["execution_refs"] = execution_refs
        successor["state_digest"] = _digest(successor, "state_digest")

        transition_receipt = {
            "schema_id": "gwc.universal-run.controller-transition-receipt.v2",
            "schema_version": 2,
            "run_id": successor["run_id"],
            "runtime_plan_digest": self.runtime_plan["digest"],
            "candidate_sha": candidate_sha,
            "from_gate": gate,
            "to_gate": successor["active_gate"],
            "transition_ref": transition_ref,
            "pre_state": {"sequence": old_sequence, "state_digest": pre_state["state_digest"]},
            "consumed_receipt_digest": receipt_digest,
            "idempotency_key": idempotency_key,
            "post_state": {"sequence": successor["sequence"], "state_digest": successor["state_digest"]},
            "kernel_completion_receipt": transition["completion_receipt"],
            "kernel_transition_receipt": transition["transition_receipt"],
            "authority_granted": False,
            "executed_effects": [],
        }
        transition_receipt["transition_digest"] = _digest(transition_receipt, "transition_digest")
        subject = {
            "runtime_epoch": self.profile["runtime_epoch"],
            "actor": "CONTROLLER",
            "next_owner": next_owner,
            "typed_next": typed_next,
            "run_id": successor["run_id"],
            "sequence": successor["sequence"],
            "transition_digest": transition_receipt["transition_digest"],
        }
        decision = {
            "schema_id": "gwc.universal-run.controller-decision.v2",
            "runtime_protocol": self.profile["runtime_protocol"],
            "decision_subject": subject,
            "decision_digest": "sha256:" + hashlib.sha256(_canonical_bytes(subject)).hexdigest(),
            "from_gate": gate,
            "next_gate": successor["active_gate"],
            "next_owner": next_owner,
            "typed_next": typed_next,
            "gate_advanced": True,
            "idempotent_replay": False,
            "consumed_receipt_digest": receipt_digest,
            "transition_receipt": transition_receipt,
            "successor_run_state": successor,
            "authority_granted": False,
            "executed_effects": [],
        }
        self.run_state = successor
        self._assignment = None
        return decision
    def complete_controller_owned_gate(
        self,
        *,
        evidence: Mapping[str, Any],
        expected_sequence: int | None = None,
        transition_receipt_ref: str | None = None,
        completion_metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Complete one Controller-owned gate from canonical evidence, separating metadata."""
        _require(isinstance(evidence, Mapping) and bool(evidence), "CONTROLLER_LOCAL_GATE_EVIDENCE_REQUIRED")
        _require(completion_metadata is None or isinstance(completion_metadata, Mapping), "CONTROLLER_LOCAL_COMPLETION_METADATA_INVALID")
        evidence_copy = copy.deepcopy(dict(evidence))
        completion_metadata_copy = copy.deepcopy(dict(completion_metadata or {}))
        current_sequence = int(self.run_state["sequence"])
        sequence = current_sequence if expected_sequence is None else expected_sequence
        _require(isinstance(sequence, int) and not isinstance(sequence, bool) and sequence >= 1, "CONTROLLER_LOCAL_GATE_SEQUENCE_INVALID")
        ledger = list(self.run_state.get("controller_local_completion_ledger", []))
        _require(all(isinstance(item, Mapping) for item in ledger), "CONTROLLER_LOCAL_COMPLETION_LEDGER_INVALID")

        sequence_entries = [item for item in ledger if item.get("sequence") == sequence]
        if sequence == current_sequence:
            gate = str(self.run_state["active_gate"])
        else:
            _require(len(sequence_entries) == 1, "CONTROLLER_LOCAL_COMPLETION_RECORD_MISSING")
            gate = str(sequence_entries[0].get("gate", ""))
        if gate == "UR.G4":
            allowed_evidence_shapes = ({"integration_outcome"}, {"INTEGRATION_RECEIPT"})
            _require(
                set(evidence_copy) in allowed_evidence_shapes,
                "CONTROLLER_LOCAL_GATE_EVIDENCE_NONCANONICAL",
                "UR.G4 evidence must contain only integration_outcome or only INTEGRATION_RECEIPT; provenance belongs in completion_metadata",
            )
        candidate_sha = str(self.runtime_plan["source_binding"]["pre_head_sha"])
        evidence_digest = "sha256:" + hashlib.sha256(_canonical_bytes(evidence_copy)).hexdigest()
        completion_metadata_digest = "sha256:" + hashlib.sha256(_canonical_bytes(completion_metadata_copy)).hexdigest()
        identity = {
            "run_id": self.run_state["run_id"],
            "runtime_plan_digest": self.runtime_plan["digest"],
            "candidate_sha": candidate_sha,
            "gate": gate,
            "sequence": sequence,
            "action": "complete_controller_owned_gate",
            "actor": "CONTROLLER",
            "evidence_digest": evidence_digest,
            "completion_metadata_digest": completion_metadata_digest,
        }
        idempotency_key = "sha256:" + hashlib.sha256(_canonical_bytes(identity)).hexdigest()
        prior_matches = [item for item in ledger if item.get("idempotency_key") == idempotency_key]
        if not prior_matches and sequence != current_sequence and sequence_entries:
            prior_for_sequence = sequence_entries[0]
            same_command = (
                prior_for_sequence.get("run_id") == self.run_state["run_id"]
                and prior_for_sequence.get("runtime_plan_digest") == self.runtime_plan["digest"]
                and prior_for_sequence.get("candidate_sha") == candidate_sha
                and prior_for_sequence.get("gate") == gate
                and prior_for_sequence.get("sequence") == sequence
                and prior_for_sequence.get("action") == "complete_controller_owned_gate"
            )
            _require(not same_command, "CONTROLLER_LOCAL_COMPLETION_IDEMPOTENCY_CONFLICT")
        _require(len(prior_matches) <= 1, "CONTROLLER_LOCAL_COMPLETION_LEDGER_INVALID")
        if prior_matches:
            prior = prior_matches[0]
            local_receipt = prior.get("receipt")
            _require(isinstance(local_receipt, Mapping), "CONTROLLER_LOCAL_COMPLETION_RECORD_INVALID")
            _require(
                prior.get("run_id") == self.run_state["run_id"]
                and prior.get("runtime_plan_digest") == self.runtime_plan["digest"]
                and prior.get("candidate_sha") == candidate_sha
                and prior.get("gate") == gate
                and prior.get("sequence") == sequence
                and local_receipt.get("idempotency_key") == idempotency_key
                and local_receipt.get("receipt_digest") == _digest(local_receipt, "receipt_digest"),
                "CONTROLLER_LOCAL_COMPLETION_IDEMPOTENCY_CONFLICT",
            )
            _require(
                local_receipt.get("evidence_digest") == evidence_digest
                and local_receipt.get("completion_metadata_digest") == completion_metadata_digest,
                "CONTROLLER_LOCAL_COMPLETION_IDEMPOTENCY_CONFLICT",
            )
            if transition_receipt_ref is not None:
                _require(
                    transition_receipt_ref == prior.get("transition_ref"),
                    "CONTROLLER_LOCAL_COMPLETION_IDEMPOTENCY_CONFLICT",
                )
            return {
                "schema_id": "gwc.universal-run.controller-decision.v2",
                "runtime_protocol": self.profile["runtime_protocol"],
                "run_id": self.run_state["run_id"],
                "sequence": self.run_state["sequence"],
                "active_gate": self.run_state["active_gate"],
                "from_gate": gate,
                "next_gate": prior["to_gate"],
                "next_owner": prior["next_owner"],
                "typed_next": prior["typed_next"],
                "gate_advanced": False,
                "idempotent_replay": True,
                "consumed_receipt_digest": local_receipt["receipt_digest"],
                "controller_local_completion_receipt": copy.deepcopy(dict(local_receipt)),
                "transition_ref": prior["transition_ref"],
                "transition_digest": prior.get("transition_digest"),
                "successor_run_state": copy.deepcopy(self.run_state),
                "authority_granted": False,
                "executed_effects": [],
            }

        _require(sequence == current_sequence, "CONTROLLER_LOCAL_GATE_SEQUENCE_MISMATCH")
        _require(self.run_state.get("active_gate") == gate, "CONTROLLER_LOCAL_GATE_MISMATCH")
        _require(self.run_state.get("next_owner") == "CONTROLLER", "CONTROLLER_LOCAL_GATE_OWNER_MISMATCH")
        assignment = self._assignment
        _require(isinstance(assignment, Mapping), "CONTROLLER_LOCAL_ACTION_NOT_ISSUED")
        _require(
            assignment.get("actor") != "EXECUTOR",
            "CONTROLLER_LOCAL_GATE_EXECUTOR_ASSIGNMENT_CONFLICT",
        )
        _require(
            assignment.get("actor") == "CONTROLLER"
            and assignment.get("run_id") == self.run_state["run_id"]
            and assignment.get("sequence") == sequence
            and assignment.get("gate") == gate
            and assignment.get("action") == Q0_ACTIONS[gate]
            and assignment.get("typed_next") == self.run_state.get("typed_next")
            and assignment.get("runtime_plan_digest") == self.runtime_plan["digest"],
            "CONTROLLER_LOCAL_GATE_ASSIGNMENT_BINDING_MISMATCH",
        )

        complete_q0_gate(
            gate=gate,
            evidence=evidence_copy,
            run_id=self.run_state["run_id"],
            runtime_plan_digest=self.runtime_plan["digest"],
            candidate_sha=candidate_sha,
        )
        local_receipt_body = {
            "schema_id": "gwc.universal-run.controller-local-completion-receipt.v2",
            "schema_version": 2,
            "runtime_protocol": self.profile["runtime_protocol"],
            "runtime_epoch": self.profile["runtime_epoch"],
            "run_id": self.run_state["run_id"],
            "runtime_plan_digest": self.runtime_plan["digest"],
            "candidate_sha": candidate_sha,
            "sequence": sequence,
            "gate": gate,
            "action": "complete_controller_owned_gate",
            "evidence": evidence_copy,
            "evidence_digest": evidence_digest,
            "completion_metadata": completion_metadata_copy,
            "completion_metadata_digest": completion_metadata_digest,
            "idempotency_key": idempotency_key,
            "pre_state_digest": self.run_state["state_digest"],
            "authority_granted": False,
            "executed_effects": [],
        }
        local_receipt = {
            **local_receipt_body,
            "receipt_digest": _digest(local_receipt_body, "receipt_digest"),
        }
        transition = advance_qualification_gate(
            current_gate=gate,
            current_state="ACTIVE",
            evidence=evidence_copy,
            sequence=sequence,
            run_id=self.run_state["run_id"],
            runtime_plan_digest=self.runtime_plan["digest"],
            candidate_sha=candidate_sha,
        )
        pre_state = copy.deepcopy(self.run_state)
        successor = copy.deepcopy(self.run_state)
        successor.pop("state_digest", None)
        successor["predecessor_sequence"] = sequence
        successor["predecessor_state_digest"] = pre_state["state_digest"]
        successor["sequence"] = sequence + int(transition["sequence_delta"])
        successor["active_gate"] = transition["next_gate"]
        successor["gate_evidence"] = evidence_copy
        successor["evidence_gap"] = list(GATE_EVIDENCE[successor["active_gate"]])
        typed_next = (
            "MATERIALIZE_UR_G3_VERIFICATION_RECEIPT"
            if successor["active_gate"] == "UR.G3"
            else "CONTINUE_UNIVERSAL_LANE_REMEDIATION"
        )
        next_owner = "EXECUTOR" if successor["active_gate"] == "UR.G3" else "CONTROLLER"
        successor["typed_next"] = typed_next
        successor["next_owner"] = next_owner
        transition_ref = transition_receipt_ref or (
            f"{successor['run_id']}:controller-local-transition:seq{sequence}-seq{successor['sequence']}:{idempotency_key}"
        )
        completion_record = {
            "run_id": successor["run_id"],
            "runtime_plan_digest": self.runtime_plan["digest"],
            "candidate_sha": candidate_sha,
            "idempotency_key": idempotency_key,
            "receipt_digest": local_receipt["receipt_digest"],
            "evidence_digest": evidence_digest,
            "completion_metadata_digest": completion_metadata_digest,
            "sequence": sequence,
            "gate": gate,
            "action": "complete_controller_owned_gate",
            "to_gate": successor["active_gate"],
            "typed_next": typed_next,
            "next_owner": next_owner,
            "transition_ref": transition_ref,
            "receipt": local_receipt,
        }
        successor["controller_local_completion_ledger"] = ledger + [completion_record]
        execution_refs = copy.deepcopy(dict(successor.get("execution_refs", {})))
        execution_refs["cursor_ref"] = f"{successor['run_id']}:{successor['active_gate']}:seq{successor['sequence']}"
        successor["execution_refs"] = execution_refs
        successor["state_digest"] = _digest(successor, "state_digest")

        transition_receipt = {
            "schema_id": "gwc.universal-run.controller-transition-receipt.v2",
            "schema_version": 2,
            "run_id": successor["run_id"],
            "runtime_plan_digest": self.runtime_plan["digest"],
            "candidate_sha": candidate_sha,
            "from_gate": gate,
            "to_gate": successor["active_gate"],
            "transition_ref": transition_ref,
            "pre_state": {"sequence": sequence, "state_digest": pre_state["state_digest"]},
            "consumed_receipt_digest": local_receipt["receipt_digest"],
            "idempotency_key": idempotency_key,
            "post_state": {"sequence": successor["sequence"], "state_digest": successor["state_digest"]},
            "kernel_completion_receipt": transition["completion_receipt"],
            "kernel_transition_receipt": transition["transition_receipt"],
            "authority_granted": False,
            "executed_effects": [],
        }
        transition_receipt["transition_digest"] = _digest(transition_receipt, "transition_digest")
        subject = {
            "runtime_epoch": self.profile["runtime_epoch"],
            "actor": "CONTROLLER",
            "next_owner": next_owner,
            "typed_next": typed_next,
            "run_id": successor["run_id"],
            "sequence": successor["sequence"],
            "transition_digest": transition_receipt["transition_digest"],
        }
        decision = {
            "schema_id": "gwc.universal-run.controller-decision.v2",
            "runtime_protocol": self.profile["runtime_protocol"],
            "decision_subject": subject,
            "decision_digest": "sha256:" + hashlib.sha256(_canonical_bytes(subject)).hexdigest(),
            "from_gate": gate,
            "next_gate": successor["active_gate"],
            "next_owner": next_owner,
            "typed_next": typed_next,
            "gate_advanced": True,
            "idempotent_replay": False,
            "consumed_receipt_digest": local_receipt["receipt_digest"],
            "controller_local_completion_receipt": local_receipt,
            "transition_receipt": transition_receipt,
            "successor_run_state": successor,
            "authority_granted": False,
            "executed_effects": [],
        }
        self.run_state = successor
        self._assignment = None
        return decision

    def record_historical_controller_evidence(
        self, raw_body: bytes | bytearray | str, *, expected_sha256: str
    ) -> dict[str, Any]:
        """Classify one byte-bound legacy incident as history without parsing it."""
        if isinstance(raw_body, str):
            raw = raw_body.encode("utf-8")
        elif isinstance(raw_body, (bytes, bytearray)):
            raw = bytes(raw_body)
        else:
            raise UniversalControllerError("HISTORICAL_EVIDENCE_BYTES_REQUIRED")
        actual = hashlib.sha256(raw).hexdigest()
        _require(actual == expected_sha256, "HISTORICAL_EVIDENCE_HASH_MISMATCH")
        return {
            "classification": "HISTORICAL_LEGACY_INCIDENT_EVIDENCE",
            "source_sha256": actual,
            "raw_payload_interpreted": False,
            "authority_effect": False,
            "runtime_state_changed": False,
            "native_cursor": {
                "run_id": self.run_state["run_id"],
                "sequence": self.run_state["sequence"],
                "active_gate": self.run_state["active_gate"],
                "state_digest": self.run_state["state_digest"],
            },
        }


__all__ = ["UniversalController", "UniversalControllerError"]
