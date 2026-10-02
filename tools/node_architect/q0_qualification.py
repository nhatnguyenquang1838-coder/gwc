"""Native Q0 runtime qualification, certification, and acceptance semantics.

Qualification and human acceptance are Universal Run concepts. This module is
pure: it creates deterministic receipts, never grants effect authority, and
never mutates a repository or starts the real workload.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from tools.node_architect.universal_run_kernel import UNIVERSAL_PROFILE, transition_lifecycle
from tools.node_architect.universal_run_lifecycle import evaluate_transition

Q0_WORKFLOW_MODE = "q0_live_qualification"
Q0_RUNTIME_EPOCH = "UNIVERSAL_V2_DEVELOPMENT"
Q0_ACCEPTANCE_GATE = "UR.G6"
Q0_INTEGRATION_GATE = "UR.G4"
LOGIN_TARGET = "LOGIN_R00_PLUS"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")

MANDATORY_QUALIFICATION_ENTRIES = (
    "fresh_boot", "default_route", "runtime_plan", "node_allocation",
    "node_architect_seam", "effect_authority", "exact_readback",
    "typed_continuation", "restart_recovery", "self_fix_replay",
    "stale_state_fail_closed", "deterministic_replay",
    "recursive_plan_dag_complete",
)

GATE_EVIDENCE = {
    "UR.G0": ("UNDERSTANDING_RECEIPT",),
    "UR.G1": ("PLAN_RECEIPT",),
    "UR.G2": ("EXECUTION_RECEIPT",),
    "UR.G3": ("VERIFICATION_RECEIPT",),
    "UR.G4": ("INTEGRATION_RECEIPT", "integration_outcome"),
    "UR.G5": ("TARGET_VALIDATION_RECEIPT",),
    "UR.G6": ("Q0_ACCEPTANCE_RECEIPT", "CLOSURE_RECEIPT", "HANDOFF_RECEIPT"),
}


class Q0QualificationError(ValueError):
    """Stable fail-closed Q0 semantic error."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code if not detail else f"{code}: {detail}")
        self.code = code


def _require(condition: bool, code: str, detail: str = "") -> None:
    if not condition:
        raise Q0QualificationError(code, detail)


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _valid_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA40.fullmatch(value))


def _valid_digest(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA256.fullmatch(value))


def _parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _sealed(artifact: dict[str, Any], field: str = "receipt_digest") -> dict[str, Any]:
    artifact[field] = _digest({k: v for k, v in artifact.items() if k != field})
    return artifact


def _verify_seal(artifact: Mapping[str, Any], field: str) -> bool:
    expected = artifact.get(field)
    return isinstance(expected, str) and expected == _digest({k: v for k, v in artifact.items() if k != field})


Q0_ACTIONS = {
    "UR.G0": "q0_understand",
    "UR.G1": "q0_plan_decompose",
    "UR.G2": "q0_execute_probe",
    "UR.G3": "q0_verify_evidence",
    "UR.G4": "q0_integrate_candidate",
    "UR.G5": "q0_validate_in_target",
    "UR.G6": "q0_accept_and_handoff",
}


Q0_REQUIRED_LOG_FIELDS = (
    "run_id", "runtime_epoch", "workflow_mode", "gate", "requested_action",
    "typed_next", "evidence_refs", "decision_digest",
)


def q0_qualification_profile() -> dict[str, Any]:
    """Load the digest-bound Q0 profile; fail closed on profile drift."""
    path = Path(__file__).resolve().parents[2] / "core/node-architect/q0-live-qualification-profile.json"
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Q0QualificationError("Q0_PROFILE_UNAVAILABLE", str(exc)) from exc
    try:
        import jsonschema
        schema_path = Path(__file__).resolve().parents[2] / "schemas/q0-live-qualification-profile.schema.json"
        jsonschema.validate(profile, json.loads(schema_path.read_text(encoding="utf-8")))
    except Exception as exc:
        raise Q0QualificationError("Q0_PROFILE_SCHEMA_INVALID", str(exc)) from exc
    digest = profile.get("profile_digest")
    body = {k: copy.deepcopy(v) for k, v in profile.items() if k != "profile_digest"}
    _require(_valid_digest(digest) and digest == _digest(body), "Q0_PROFILE_DIGEST_INVALID")
    expected_nodes = {gate: {"node_id": "q0.qualification-campaign", "action": action} for gate, action in Q0_ACTIONS.items()}
    _require(profile.get("qualification_campaign") is True, "Q0_PROFILE_BINDING_INVALID")
    _require(profile.get("mandatory_qualification_entries") == list(MANDATORY_QUALIFICATION_ENTRIES), "Q0_PROFILE_MATRIX_MISMATCH")
    _require(profile.get("qualification_nodes") == expected_nodes, "Q0_PROFILE_NODE_MAP_INVALID")
    _require(profile.get("completion_evidence") == {k:list(v) for k,v in GATE_EVIDENCE.items()}, "Q0_PROFILE_EVIDENCE_MAP_INVALID")
    _require(tuple(profile.get("required_log_fields", [])) == Q0_REQUIRED_LOG_FIELDS, "Q0_PROFILE_LOG_CONTRACT_INVALID")
    _require(profile.get("workflow_mode") == Q0_WORKFLOW_MODE and profile.get("runtime_epoch") == Q0_RUNTIME_EPOCH, "Q0_PROFILE_BINDING_INVALID")
    _require(profile.get("runtime_profile") == UNIVERSAL_PROFILE, "Q0_UNIVERSAL_PROFILE_BINDING_INVALID")
    return profile


def validate_q0_route_context(context: Mapping[str, Any]) -> dict[str, Any]:
    """Validate Q0 runtime identity and its independent effect boundary."""
    payload = dict(context or {})
    if payload.get("workflow_mode") != Q0_WORKFLOW_MODE:
        return {"permitted": False, "reason_code": "Q0_WORKFLOW_MODE_REQUIRED"}
    if payload.get("runtime_epoch") != Q0_RUNTIME_EPOCH:
        return {"permitted": False, "reason_code": "Q0_RUNTIME_EPOCH_MISMATCH"}
    if str(payload.get("task_id")) != "SCRUM-781" or not str(payload.get("run_id", "")):
        return {"permitted": False, "reason_code": "Q0_RUN_BINDING_REQUIRED"}
    if payload.get("gate") not in {f"UR.G{i}" for i in range(7)}:
        return {"permitted": False, "reason_code": "Q0_UNIVERSAL_GATE_REQUIRED"}
    if payload.get("q0_profile") != q0_qualification_profile():
        return {"permitted": False, "reason_code": "Q0_PROFILE_BINDING_MISMATCH"}
    effect_class = payload.get("effect_class")
    if effect_class == "read_only":
        return {"permitted": True, "reason_code": "Q0_READ_ONLY_ROUTE", "authority_granted": False}
    if effect_class == "branch_local_write":
        decision = payload.get("q0_effect_authority_decision")
        exact = isinstance(decision, Mapping) and all((
            decision.get("status") == "AUTHORIZED",
            decision.get("task_id") == payload.get("task_id"),
            decision.get("run_id") == payload.get("run_id"),
            decision.get("action") == payload.get("requested_action"),
            decision.get("branch") == "fix/SCRUM-781-q0-canonical",
            decision.get("runtime_epoch") == Q0_RUNTIME_EPOCH,
        ))
        return {"permitted": bool(exact), "reason_code": "Q0_BRANCH_EFFECT_AUTHORIZED" if exact else "Q0_EFFECT_AUTHORITY_REQUIRED", "authority_granted": False}
    return {"permitted": False, "reason_code": "Q0_EXTERNAL_EFFECT_OUT_OF_SCOPE"}


def resolve_q0_qualification_node(context: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve a Q0 gate to a qualification node in Node Architect's route surface."""
    payload = dict(context or {})
    authority = validate_q0_route_context(payload)
    if not authority.get("permitted"):
        return authority
    gate = str(payload.get("gate"))
    profile = q0_qualification_profile()
    node = profile["qualification_nodes"][gate]
    if payload.get("requested_action") != node["action"]:
        return {"permitted": False, "reason_code": "Q0_NODE_ACTION_MISMATCH"}
    return {
        "permitted": True, "reason_code": "Q0_QUALIFICATION_NODE_SELECTED",
        "workflow_mode": Q0_WORKFLOW_MODE, "runtime_epoch": Q0_RUNTIME_EPOCH,
        "profile_id": profile["profile_id"], "profile_revision": profile["revision"],
        "profile_digest": profile["profile_digest"], "gate": gate,
        "route_id": f"q0-{gate.lower().replace('.', '-')}",
        "current_node": node["node_id"], "requested_action": node["action"],
        "node_instruction_ref": "core/node-architect/node-instructions/q0/qualification-campaign.node-instruction.yaml",
        "node_descriptor_ref": "core/node-architect/q0/qualification-campaign.node.json",
        "implementation_ref": "tools/node_architect/q0_qualification.py:resolve_q0_qualification_node",
        "next_node": None, "next_action": "q0_continue_universal_lifecycle", "next_gate": None, "authority_granted": False,
        "log_contract_valid": tuple(profile.get("required_log_fields", [])) == Q0_REQUIRED_LOG_FIELDS,
        "evidence_contract_valid": profile.get("completion_evidence") == {k:list(v) for k,v in GATE_EVIDENCE.items()},
    }


def complete_q0_gate(
    *, gate: str, evidence: Mapping[str, Any], run_id: str | None = None,
    runtime_plan_digest: str | None = None,
) -> dict[str, Any]:
    """Validate the completion evidence for one namespaced Universal gate."""
    _require(gate in GATE_EVIDENCE, "Q0_GATE_UNKNOWN", str(gate))
    values = dict(evidence or {})
    required = GATE_EVIDENCE[gate]
    if gate == "UR.G4":
        outcome = values.get("integration_outcome")
        receipt = values.get("INTEGRATION_RECEIPT")
        valid_outcome = outcome in {"INTEGRATED", "IN_PLACE", "NO_TRANSFER_REQUIRED", "DOMAIN_DEFINED"}
        _require(bool(receipt) or valid_outcome, "INTEGRATION_EVIDENCE_REQUIRED")
        return {"gate": gate, "gate_state": "PASSED", "evidence_kind": "INTEGRATION_RECEIPT" if receipt else outcome}
    if gate == "UR.G2":
        receipt = values.get("EXECUTION_RECEIPT")
        _require(bool(receipt), "EXECUTION_EVIDENCE_REQUIRED")
        valid_refs = (
            isinstance(receipt, Mapping)
            and isinstance(receipt.get("evidence_refs"), Mapping)
            and bool(receipt.get("evidence_refs"))
            and all(isinstance(ref, str) and bool(ref.strip()) for ref in receipt.get("evidence_refs", {}).values())
        )
        expected_node_id = q0_qualification_profile()["qualification_nodes"]["UR.G2"]["node_id"]
        valid_receipt = (
            isinstance(receipt, Mapping)
            and receipt.get("schema_id") == "gwc.universal-run.execution-receipt"
            and receipt.get("artifact_type") == "universal-run-execution-receipt"
            and receipt.get("gate") == "UR.G2"
            and receipt.get("runtime_epoch") == Q0_RUNTIME_EPOCH
            and receipt.get("route_id") == "UNIVERSAL_RUN_NEW_RUNTIME"
            and receipt.get("host_status") == "SEMANTIC_NODE_COMPLETE"
            and _valid_digest(receipt.get("runtime_plan_digest"))
            and _valid_digest(receipt.get("host_result_digest"))
            and isinstance(receipt.get("run_id"), str) and bool(receipt.get("run_id"))
            and isinstance(receipt.get("node_id"), str) and receipt.get("node_id") == expected_node_id
            and isinstance(receipt.get("node_allocation_id"), str)
            and receipt.get("node_allocation_id") == f"{receipt.get('run_id')}:{expected_node_id}"
            and isinstance(receipt.get("event_id"), str) and bool(receipt.get("event_id"))
            and receipt.get("authority_granted") is False
            and receipt.get("executed_effects") == []
            and valid_refs
            and _verify_seal(receipt, "receipt_digest")
        )
        _require(valid_receipt, "EXECUTION_RECEIPT_INVALID")
        if not isinstance(receipt, Mapping):
            raise Q0QualificationError("EXECUTION_RECEIPT_INVALID")
        if run_id is not None:
            _require(receipt.get("run_id") == run_id, "EXECUTION_RECEIPT_RUN_MISMATCH")
        if runtime_plan_digest is not None:
            _require(receipt.get("runtime_plan_digest") == runtime_plan_digest, "EXECUTION_RECEIPT_PLAN_MISMATCH")
        return {"gate": gate, "gate_state": "PASSED", "evidence_kind": "EXECUTION_RECEIPT"}
    if gate == "UR.G6":
        acceptance = values.get("Q0_ACCEPTANCE_RECEIPT")
        closure = values.get("CLOSURE_RECEIPT")
        handoff = values.get("HANDOFF_RECEIPT")
        _require(isinstance(acceptance, Mapping) and acceptance.get("artifact_type") == "q0-acceptance-decision-receipt" and acceptance.get("decision") == "ACCEPT" and acceptance.get("decision_authority") == {"type":"human", "id":"NHAT"} and acceptance.get("effect_authority_granted") is False and acceptance.get("consumed") is True and _verify_seal(acceptance, "receipt_digest"), "Q0_ACCEPTANCE_RECEIPT_REQUIRED")
        _require(isinstance(closure, Mapping) and closure.get("artifact_type") == "closure-receipt" and closure.get("gate") == "UR.G6" and closure.get("closure_outcome") == "ACCEPTED" and _verify_seal(closure, "receipt_digest"), "CLOSURE_RECEIPT_REQUIRED")
        _require(isinstance(handoff, Mapping) and handoff.get("artifact_type") == "handoff-receipt" and handoff.get("target") == LOGIN_TARGET and handoff.get("status") == "Q0_ACCEPTED_AUTONOMOUS_HANDOFF" and _verify_seal(handoff, "receipt_digest"), "HANDOFF_RECEIPT_REQUIRED")
        _require(closure.get("acceptance_receipt_ref") == acceptance.get("receipt_digest") and handoff.get("acceptance_receipt_ref") == acceptance.get("receipt_digest") and handoff.get("closure_receipt_ref") == closure.get("receipt_digest"), "Q0_G6_RECEIPT_BINDING_MISMATCH")
        _require(acceptance.get("certified_q0_sha") == handoff.get("certified_q0_sha") and acceptance.get("run_id") == closure.get("run_id") == handoff.get("run_id"), "Q0_G6_RECEIPT_BINDING_MISMATCH")
        return {"gate": gate, "gate_state": "PASSED", "evidence_kind": list(required)}
    reason = {
        "UR.G0": "UNDERSTANDING_RECEIPT_REQUIRED",
        "UR.G1": "PLAN_RECEIPT_REQUIRED",
        "UR.G2": "EXECUTION_EVIDENCE_REQUIRED",
        "UR.G3": "VERIFICATION_RECEIPT_REQUIRED",
        "UR.G5": "TARGET_VALIDATION_RECEIPT_REQUIRED",
    }[gate]
    _require(bool(values.get(required[0])), reason)
    return {"gate": gate, "gate_state": "PASSED", "evidence_kind": required[0]}


def advance_qualification_gate(
    *, current_gate: str, current_state: str, evidence: Mapping[str, Any], sequence: int = 1,
    run_id: str | None = None, runtime_plan_digest: str | None = None,
) -> dict[str, Any]:
    """Use the shared Universal kernel lifecycle to complete then advance one gate."""
    complete_q0_gate(
        gate=current_gate, evidence=evidence, run_id=run_id,
        runtime_plan_digest=runtime_plan_digest,
    )
    gate = current_gate.removeprefix("UR.")
    outcome = (evidence or {}).get("integration_outcome") if current_gate == "UR.G4" else None
    if current_gate == "UR.G4" and outcome is None and (evidence or {}).get("INTEGRATION_RECEIPT"):
        outcome = "INTEGRATED"
    completed = evaluate_transition(
        profile=UNIVERSAL_PROFILE, current_gate=gate, current_state=current_state,
        action="COMPLETE", explicit_outcome=outcome,
    ).to_dict()
    passed_state = completed["outcome"]["next_state"]
    advanced = evaluate_transition(
        profile=UNIVERSAL_PROFILE, current_gate=gate, current_state=passed_state,
        action="ADVANCE",
    ).to_dict()
    return {
        "current_gate": current_gate,
        "next_gate": "UR." + advanced["outcome"]["next_gate"],
        "next_state": advanced["outcome"]["next_state"],
        "sequence_delta": 1,
        "transition_receipt": advanced["receipt"],
        "completion_receipt": completed["receipt"],
    }


def _validate_matrix(matrix: Mapping[str, Any]) -> None:
    _require(isinstance(matrix, Mapping), "QUALIFICATION_MATRIX_REQUIRED")
    digest = matrix.get("digest")
    _require(_valid_digest(digest), "QUALIFICATION_MATRIX_DIGEST_INVALID")
    matrix_body = {k: copy.deepcopy(v) for k, v in matrix.items() if k != "digest"}
    _require(digest == _digest(matrix_body), "QUALIFICATION_MATRIX_DIGEST_MISMATCH")
    declared_mandatory = matrix.get("mandatory_entries")
    _require(isinstance(declared_mandatory, list) and tuple(declared_mandatory) == MANDATORY_QUALIFICATION_ENTRIES, "QUALIFICATION_MATRIX_PROFILE_MISMATCH")
    results = matrix.get("results")
    _require(isinstance(results, Mapping), "QUALIFICATION_MATRIX_INCOMPLETE")
    missing = [name for name in MANDATORY_QUALIFICATION_ENTRIES if results.get(name) != "PASS"]
    _require(not missing, "QUALIFICATION_MATRIX_INCOMPLETE", ",".join(missing))
    _require(not list(matrix.get("active_unresolved_defects") or []), "ACTIVE_Q0_DEFECTS")


def certify_q0_runtime(
    *, run_id: str, task_id: str, runtime_epoch: str, qualification_profile: str,
    qualification_profile_digest: str, qualification_matrix: Mapping[str, Any], candidate_sha: str,
    loaded_runtime_identity: str, load_proof_ref: str, load_proof_evidence: Mapping[str, Any],
    incident_replay_refs: list[str], replay_result: str, replay_exact_readback: bool,
    previous_failure_state: str, first_state_beyond_failure: str,
    forward_progress_refs: list[str], broader_regression_refs: list[str], broader_regression_result: str,
    stale_dependent_state: list[str], created_at: str, created_by: Mapping[str, Any],
) -> dict[str, Any]:
    """Certify only a complete, exact-identity Q0 campaign (L3)."""
    _require(bool(run_id and task_id), "Q0_BINDING_REQUIRED")
    _require(task_id == "SCRUM-781", "Q0_TASK_MISMATCH")
    _require(runtime_epoch == Q0_RUNTIME_EPOCH, "Q0_RUNTIME_EPOCH_MISMATCH")
    _require(qualification_profile == Q0_WORKFLOW_MODE, "Q0_PROFILE_MISMATCH")
    _require(_valid_digest(qualification_profile_digest) and qualification_profile_digest == q0_qualification_profile().get("profile_digest"), "Q0_PROFILE_DIGEST_MISMATCH")
    _require(_valid_sha(candidate_sha), "CANDIDATE_SHA_INVALID")
    _require(_valid_sha(loaded_runtime_identity), "RUNTIME_IDENTITY_INVALID")
    _require(loaded_runtime_identity == candidate_sha, "RUNTIME_IDENTITY_DRIFT")
    _require(bool(load_proof_ref), "LOAD_PROOF_REQUIRED")
    _require(isinstance(load_proof_evidence, Mapping) and bool(load_proof_evidence.get("activation_id")) and bool(load_proof_evidence.get("source_root")), "LOAD_PROOF_REQUIRED")
    _require(bool(load_proof_evidence.get("runtime_session_id")) and bool(load_proof_evidence.get("runtime_process_id")), "LOAD_PROOF_PROCESS_IDENTITY_REQUIRED")
    _require(load_proof_evidence.get("loaded_profile_digest") == qualification_profile_digest, "LOAD_PROOF_PROFILE_IDENTITY_MISMATCH")
    module_identities = load_proof_evidence.get("loaded_module_identities")
    if not isinstance(module_identities, Mapping) or not module_identities:
        raise Q0QualificationError("LOAD_PROOF_MODULE_IDENTITIES_REQUIRED")
    _require(all(isinstance(path, str) and path and _valid_digest(digest) for path, digest in module_identities.items()), "LOAD_PROOF_MODULE_IDENTITIES_INVALID")
    _require(load_proof_evidence.get("candidate_sha") == candidate_sha and load_proof_evidence.get("loaded_source_sha") == candidate_sha, "LOAD_PROOF_IDENTITY_MISMATCH")
    _validate_matrix(qualification_matrix)
    _require(bool(incident_replay_refs), "ORIGINAL_INCIDENT_REPLAY_REQUIRED")
    _require(replay_result == "PASS" and replay_exact_readback is True, "ORIGINAL_INCIDENT_REPLAY_FAILED")
    _require(bool(previous_failure_state) and bool(first_state_beyond_failure) and first_state_beyond_failure != previous_failure_state, "FORWARD_PROGRESS_REQUIRED")
    _require(bool(forward_progress_refs), "FORWARD_PROGRESS_REQUIRED")
    _require(bool(broader_regression_refs) and broader_regression_result == "PASS", "BROADER_REGRESSION_REQUIRED")
    _require(not list(stale_dependent_state or []), "STALE_DEPENDENT_STATE_REMAINS")
    _require(isinstance(created_by, Mapping) and bool(created_by.get("id")), "Q0_CREATOR_REQUIRED")
    _require(_parse_utc(created_at) is not None, "Q0_CERTIFICATION_TIMESTAMP_INVALID")
    body = {
        "schema_version": "1.0", "artifact_type": "q0-certification-receipt",
        "run_id": run_id, "task_id": task_id, "runtime_epoch": runtime_epoch,
        "qualification_profile": qualification_profile,
        "qualification_profile_digest": qualification_profile_digest,
        "qualification_matrix_digest": qualification_matrix["digest"],
        "candidate_sha": candidate_sha, "loaded_runtime_identity": loaded_runtime_identity,
        "load_proof_ref": load_proof_ref,
        "load_proof_evidence": copy.deepcopy(dict(load_proof_evidence)),
        "incident_replay_refs": list(incident_replay_refs),
        "replay_result": replay_result, "replay_exact_readback": replay_exact_readback,
        "previous_failure_state": previous_failure_state,
        "first_state_beyond_failure": first_state_beyond_failure,
        "forward_progress_refs": list(forward_progress_refs),
        "broader_regression_refs": list(broader_regression_refs),
        "broader_regression_result": broader_regression_result,
        "stale_dependent_state": list(stale_dependent_state or []),
        "certified_q0_sha": candidate_sha, "certification_level": "L3",
        "campaign_state": "CAMPAIGN_READY_RUNTIME", "created_at": created_at,
        "created_by": copy.deepcopy(dict(created_by)),
    }
    return _sealed(body)


def verify_q0_certification(receipt: Mapping[str, Any]) -> bool:
    try:
        return (
            receipt.get("artifact_type") == "q0-certification-receipt"
            and receipt.get("certification_level") == "L3"
            and receipt.get("campaign_state") == "CAMPAIGN_READY_RUNTIME"
            and receipt.get("candidate_sha") == receipt.get("certified_q0_sha") == receipt.get("loaded_runtime_identity")
            and _verify_seal(receipt, "receipt_digest")
        )
    except Exception:
        return False


def create_q0_acceptance_request(
    *, run_id: str, task_id: str, certified_q0_sha: str,
    q0_certification_receipt_ref: str, qualification_matrix_digest: str,
    target_handoff: str, decision_authority: Mapping[str, Any],
    captured_via: Mapping[str, Any], issued_at: str, expires_at: str,
) -> dict[str, Any]:
    _require(_valid_sha(certified_q0_sha), "CERTIFIED_SHA_INVALID")
    _require(bool(run_id and task_id) and task_id == "SCRUM-781", "Q0_ACCEPTANCE_BINDING_REQUIRED")
    _require(SHA256.fullmatch(q0_certification_receipt_ref) is not None, "Q0_CERTIFICATION_REF_INVALID")
    _require(_valid_digest(qualification_matrix_digest), "QUALIFICATION_MATRIX_DIGEST_INVALID")
    _require(target_handoff == LOGIN_TARGET, "Q0_HANDOFF_TARGET_INVALID")
    _require(dict(decision_authority or {}) == {"type": "human", "id": "NHAT"}, "Q0_DECISION_AUTHORITY_INVALID")
    _require(isinstance(captured_via, Mapping) and captured_via.get("type") in {"direct_chat", "approver_bot", "other_adapter"}, "Q0_CAPTURE_ADAPTER_INVALID")
    issued = _parse_utc(issued_at)
    expires = _parse_utc(expires_at)
    _require(issued is not None and expires is not None and expires > issued, "Q0_ACCEPTANCE_EXPIRY_INVALID")
    body = {
        "schema_version": "1.0", "artifact_type": "q0-acceptance-request",
        "run_id": run_id, "task_id": task_id, "certified_q0_sha": certified_q0_sha,
        "q0_certification_receipt_ref": q0_certification_receipt_ref,
        "qualification_matrix_digest": qualification_matrix_digest,
        "target_handoff": target_handoff,
        "decision_authority": dict(decision_authority), "captured_via": dict(captured_via),
        "issued_at": issued_at, "expires_at": expires_at,
        "effect_authority_granted": False,
    }
    return _sealed(body, "request_digest")


def decide_q0_acceptance(
    *, request: Mapping[str, Any], decision: str, actor: Mapping[str, Any],
    decided_at: str, current_certified_q0_sha: str,
    prior_receipt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    _require(request.get("artifact_type") == "q0-acceptance-request" and _verify_seal(request, "request_digest"), "Q0_ACCEPTANCE_REQUEST_INVALID")
    _require(request.get("decision_authority") == {"type":"human", "id":"NHAT"} and request.get("target_handoff") == LOGIN_TARGET, "Q0_DECISION_AUTHORITY_INVALID")
    _require(dict(actor or {}) == {"type": "human", "id": "NHAT"}, "Q0_DECISION_ACTOR_INVALID")
    _require(_valid_sha(current_certified_q0_sha) and current_certified_q0_sha == request.get("certified_q0_sha"), "CERTIFIED_SHA_MISMATCH")
    if prior_receipt:
        same = prior_receipt.get("request_digest") == request.get("request_digest") and prior_receipt.get("decision") == decision
        _require(same, "ACCEPTANCE_ALREADY_CONSUMED")
        return copy.deepcopy(dict(prior_receipt))
    _require(decision in {"ACCEPT", "REJECT"}, "Q0_DECISION_INVALID")
    decided = _parse_utc(decided_at)
    issued = _parse_utc(request.get("issued_at"))
    expires = _parse_utc(request.get("expires_at"))
    _require(decided is not None and issued is not None and expires is not None and issued <= decided < expires, "Q0_ACCEPTANCE_REQUEST_EXPIRED")
    body = {
        "schema_version": "1.0", "artifact_type": "q0-acceptance-decision-receipt",
        "run_id": request["run_id"], "task_id": request["task_id"],
        "certified_q0_sha": request["certified_q0_sha"],
        "q0_certification_receipt_ref": request["q0_certification_receipt_ref"],
        "qualification_matrix_digest": request["qualification_matrix_digest"],
        "target_handoff": request["target_handoff"], "decision": decision,
        "decision_authority": dict(request["decision_authority"]),
        "decided_by": dict(actor), "captured_via": dict(request["captured_via"]),
        "decided_at": decided_at, "request_digest": request["request_digest"],
        "consumed": True, "effect_authority_granted": False,
    }
    return _sealed(body)


def create_q0_accepted_handoff(*, certification: Mapping[str, Any], acceptance: Mapping[str, Any], created_at: str) -> dict[str, Any]:
    _require(verify_q0_certification(certification), "Q0_CERTIFICATION_INVALID")
    _require(acceptance.get("artifact_type") == "q0-acceptance-decision-receipt" and acceptance.get("decision") == "ACCEPT" and _verify_seal(acceptance, "receipt_digest"), "Q0_ACCEPTANCE_RECEIPT_REQUIRED")
    _require(acceptance.get("certified_q0_sha") == certification.get("certified_q0_sha"), "CERTIFIED_SHA_MISMATCH")
    _require(acceptance.get("run_id") == certification.get("run_id") and acceptance.get("task_id") == certification.get("task_id"), "Q0_HANDOFF_BINDING_MISMATCH")
    _require(acceptance.get("q0_certification_receipt_ref") == certification.get("receipt_digest"), "Q0_CERTIFICATION_REF_MISMATCH")
    _require(acceptance.get("qualification_matrix_digest") == certification.get("qualification_matrix_digest"), "Q0_MATRIX_DIGEST_MISMATCH")
    closure = _sealed({
        "schema_version": "1.0", "artifact_type": "closure-receipt", "run_id": certification["run_id"],
        "gate": "UR.G6", "closure_outcome": "ACCEPTED", "acceptance_receipt_ref": acceptance["receipt_digest"],
        "closed_at": created_at,
    })
    handoff = _sealed({
        "schema_version": "1.0", "artifact_type": "handoff-receipt", "run_id": certification["run_id"],
        "target": LOGIN_TARGET, "certified_q0_sha": certification["certified_q0_sha"],
        "acceptance_receipt_ref": acceptance["receipt_digest"], "closure_receipt_ref": closure["receipt_digest"],
        "status": "Q0_ACCEPTED_AUTONOMOUS_HANDOFF", "created_at": created_at,
    })
    return {"acceptance": copy.deepcopy(dict(acceptance)), "closure": closure, "handoff": handoff,
            "status": "Q0_ACCEPTED_AUTONOMOUS_HANDOFF", "effect_authority_granted": False}


def can_start_login_r00(*, certification: Mapping[str, Any], acceptance: Mapping[str, Any] | None) -> bool:
    _require(verify_q0_certification(certification), "CAMPAIGN_NOT_READY_L3")
    _require(certification.get("certification_level") == "L3", "CAMPAIGN_NOT_READY_L3")
    _require(isinstance(acceptance, Mapping) and acceptance.get("status") == "Q0_ACCEPTED_AUTONOMOUS_HANDOFF", "Q0_ACCEPTED_HANDOFF_REQUIRED")
    decision = acceptance.get("acceptance", {})
    handoff = acceptance.get("handoff", {})
    closure = acceptance.get("closure", {})
    _require(decision.get("decision") == "ACCEPT" and _verify_seal(decision, "receipt_digest"), "Q0_ACCEPTANCE_RECEIPT_REQUIRED")
    _require(handoff.get("target") == LOGIN_TARGET and handoff.get("certified_q0_sha") == certification.get("certified_q0_sha"), "Q0_HANDOFF_BINDING_MISMATCH")
    _require(decision.get("run_id") == certification.get("run_id") and decision.get("task_id") == certification.get("task_id"), "Q0_HANDOFF_BINDING_MISMATCH")
    _require(handoff.get("run_id") == certification.get("run_id") and handoff.get("acceptance_receipt_ref") == decision.get("receipt_digest"), "Q0_HANDOFF_BINDING_MISMATCH")
    _require(closure.get("run_id") == certification.get("run_id") and handoff.get("closure_receipt_ref") == closure.get("receipt_digest"), "Q0_CLOSURE_BINDING_MISMATCH")
    _require(closure.get("closure_outcome") == "ACCEPTED" and closure.get("gate") == "UR.G6" and _verify_seal(closure, "receipt_digest"), "Q0_CLOSURE_REQUIRED")
    _require(handoff.get("status") == "Q0_ACCEPTED_AUTONOMOUS_HANDOFF" and _verify_seal(handoff, "receipt_digest"), "Q0_HANDOFF_BINDING_MISMATCH")
    return True


__all__ = [
    "Q0_ACCEPTANCE_GATE", "Q0_INTEGRATION_GATE", "Q0QualificationError",
    "advance_qualification_gate", "can_start_login_r00", "certify_q0_runtime",
    "complete_q0_gate", "create_q0_acceptance_request", "create_q0_accepted_handoff",
    "decide_q0_acceptance", "q0_qualification_profile", "resolve_q0_qualification_node", "validate_q0_route_context", "verify_q0_certification",
]
