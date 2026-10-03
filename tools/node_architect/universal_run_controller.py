"""Native Universal Runtime v2 Controller.

The Controller owns the plan/state cursor and actor assignment. It has no
mailbox, history-controller, or transport dependency; adapters receive decisions
only after this native state has been validated.
"""
from __future__ import annotations

import copy
import hashlib
import json
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
        """Assign exactly one bounded action from the native active gate."""
        gate = str(self.run_state["active_gate"])
        action = Q0_ACTIONS[gate]
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
        idempotency_key = "sha256:" + hashlib.sha256(_canonical_bytes(identity)).hexdigest()
        scope = {
            "repository": source_binding["repository"],
            "branch": source_binding["branch"],
            "base_sha": execution_refs.get("base_sha"),
            "head_sha": execution_refs.get("candidate_sha"),
            "scope_hash": idempotency_key,
        }
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
        self._assignment = {**body, "assignment_digest": "sha256:" + hashlib.sha256(_canonical_bytes(body)).hexdigest()}
        return dict(self._assignment)
    def consume_executor_receipt(self, receipt: Mapping[str, Any]) -> dict[str, Any]:
        """Validate one actor receipt and advance only the native cursor."""
        assignment = self._assignment
        _require(isinstance(assignment, Mapping), "EXECUTOR_ASSIGNMENT_NOT_ISSUED")
        _require(isinstance(receipt, Mapping), "EXECUTOR_RECEIPT_INVALID")
        _require(
            not any(key in receipt for key in ("typed_next", "successor_run_state", "controller_decision", "next_gate")),
            "EXECUTOR_CONTROL_FIELD_FORBIDDEN",
        )
        _require(receipt.get("schema_id") == "gwc.universal-run.executor-action-receipt.v2", "EXECUTOR_RECEIPT_SCHEMA_MISMATCH")
        _require(receipt.get("runtime_protocol") == self.profile["runtime_protocol"], "EXECUTOR_RECEIPT_PROTOCOL_MISMATCH")
        _require(receipt.get("runtime_epoch") == self.profile["runtime_epoch"], "EXECUTOR_RECEIPT_EPOCH_MISMATCH")
        _require(receipt.get("run_id") == assignment["run_id"], "EXECUTOR_RECEIPT_RUN_MISMATCH")
        _require(receipt.get("sequence") == assignment["sequence"], "EXECUTOR_RECEIPT_SEQUENCE_MISMATCH")
        _require(receipt.get("gate") == assignment["gate"], "EXECUTOR_RECEIPT_GATE_MISMATCH")
        _require(receipt.get("action") == assignment["action"], "EXECUTOR_RECEIPT_ACTION_MISMATCH")
        _require(receipt.get("node_id") == assignment["node_id"], "EXECUTOR_RECEIPT_NODE_MISMATCH")
        _require(receipt.get("node_allocation_id") == assignment["node_allocation_id"], "EXECUTOR_RECEIPT_ALLOCATION_MISMATCH")
        _require(receipt.get("runtime_plan_digest") == assignment["runtime_plan_digest"], "EXECUTOR_RECEIPT_PLAN_MISMATCH")
        _require(receipt.get("assignment_digest") == assignment["assignment_digest"], "EXECUTOR_RECEIPT_ASSIGNMENT_MISMATCH")
        _require(receipt.get("host_status") == "ACTION_COMPLETE", "EXECUTOR_ACTION_NOT_COMPLETE")
        _require(receipt.get("authority_granted") is False and receipt.get("executed_effects") == [], "EXECUTOR_EFFECT_BOUNDARY_VIOLATION")
        _require(receipt.get("receipt_digest") == _digest(receipt, "receipt_digest"), "EXECUTOR_RECEIPT_DIGEST_INVALID")

        evidence = copy.deepcopy(self.run_state.get("gate_evidence", {}))
        evidence["EXECUTION_RECEIPT"] = dict(receipt)
        complete_q0_gate(
            gate=assignment["gate"],
            evidence={"EXECUTION_RECEIPT": dict(receipt)},
            run_id=assignment["run_id"],
            runtime_plan_digest=assignment["runtime_plan_digest"],
        )
        transition = advance_qualification_gate(
            current_gate=assignment["gate"],
            current_state="ACTIVE",
            evidence={"EXECUTION_RECEIPT": dict(receipt)},
            sequence=int(self.run_state["sequence"]),
            run_id=assignment["run_id"],
            runtime_plan_digest=assignment["runtime_plan_digest"],
        )
        successor = copy.deepcopy(self.run_state)
        successor.pop("state_digest", None)
        successor["predecessor_sequence"] = successor["sequence"]
        successor["sequence"] = int(successor["sequence"]) + int(transition["sequence_delta"])
        successor["active_gate"] = transition["next_gate"]
        successor["gate_evidence"] = evidence
        consumed = list(successor.get("consumed_receipts", []))
        consumed.append(receipt["receipt_digest"])
        successor["consumed_receipts"] = consumed
        execution_refs = copy.deepcopy(dict(successor.get("execution_refs", {})))
        execution_refs["cursor_ref"] = f"{successor['run_id']}:{successor['active_gate']}:seq{successor['sequence']}"
        successor["execution_refs"] = execution_refs
        successor["state_digest"] = _digest(successor, "state_digest")

        typed_next = "CONTINUE_UNIVERSAL_LANE_REMEDIATION"
        subject = {
            "runtime_epoch": self.profile["runtime_epoch"],
            "actor": "CONTROLLER",
            "typed_next": typed_next,
            "run_id": successor["run_id"],
            "sequence": successor["sequence"],
        }
        decision = {
            "schema_id": "gwc.universal-run.controller-decision.v2",
            "runtime_protocol": self.profile["runtime_protocol"],
            "decision_subject": subject,
            "decision_digest": "sha256:" + hashlib.sha256(_canonical_bytes(subject)).hexdigest(),
            "from_gate": assignment["gate"],
            "next_gate": transition["next_gate"],
            "next_owner": "CONTROLLER",
            "typed_next": typed_next,
            "gate_advanced": True,
            "consumed_receipt_digest": receipt["receipt_digest"],
            "successor_run_state": successor,
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
