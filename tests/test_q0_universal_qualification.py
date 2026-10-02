from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MOD = "tools.node_architect.q0_qualification"


def _m():
    return importlib.import_module(MOD)


def _sha(ch):
    return ch * 40


def _execution_receipt(*, authority_granted: bool = False, node_id: str = "q0.qualification-campaign"):
    run_id = "scrum781-q0-20260920T074727Z"
    body = {
        "schema_id": "gwc.universal-run.execution-receipt",
        "artifact_type": "universal-run-execution-receipt",
        "run_id": run_id,
        "runtime_epoch": "UNIVERSAL_V2_DEVELOPMENT",
        "route_id": "UNIVERSAL_RUN_NEW_RUNTIME",
        "runtime_plan_digest": "sha256:" + "a" * 64,
        "node_allocation_id": f"{run_id}:{node_id}",
        "node_id": node_id,
        "gate": "UR.G2",
        "sequence": 3,
        "event_id": "q0-execution-test",
        "host_status": "SEMANTIC_NODE_COMPLETE",
        "host_result_digest": "sha256:" + "b" * 64,
        "evidence_refs": {"node-result": ".gwc/node-result.json"},
        "authority_granted": authority_granted,
        "executed_effects": [],
    }
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    import hashlib
    return {**body, "receipt_digest": "sha256:" + hashlib.sha256(raw).hexdigest()}


def _matrix():
    body = {
        "mandatory_entries": ["fresh_boot", "default_route", "runtime_plan", "node_allocation", "node_architect_seam", "effect_authority", "exact_readback", "typed_continuation", "restart_recovery", "self_fix_replay", "stale_state_fail_closed", "deterministic_replay", "recursive_plan_dag_complete"],
        "results": {k: "PASS" for k in ["fresh_boot", "default_route", "runtime_plan", "node_allocation", "node_architect_seam", "effect_authority", "exact_readback", "typed_continuation", "restart_recovery", "self_fix_replay", "stale_state_fail_closed", "deterministic_replay", "recursive_plan_dag_complete"]},
        "active_unresolved_defects": [],
    }
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    import hashlib
    return {"digest": "sha256:" + hashlib.sha256(raw).hexdigest(), **body}


def _cert_inputs(**overrides):
    d = {
        "run_id": "scrum781-q0-20260920T074727Z",
        "task_id": "SCRUM-781",
        "runtime_epoch": "UNIVERSAL_V2_DEVELOPMENT",
        "qualification_profile": "q0_live_qualification",
        "qualification_profile_digest": _m().q0_qualification_profile()["profile_digest"],
        "qualification_matrix": _matrix(),
        "candidate_sha": _sha("a"),
        "loaded_runtime_identity": _sha("a"),
        "load_proof_ref": "load-proof:1",
        "load_proof_evidence": {"activation_id":"act-1", "candidate_sha":_sha("a"), "loaded_source_sha":_sha("a"), "source_root":"worktree:q0", "runtime_session_id":"20260923_175734_bea63d", "runtime_process_id":"runtime:test-1", "loaded_profile_digest":_m().q0_qualification_profile()["profile_digest"], "loaded_module_identities":{"tools/node_architect/q0_qualification.py":"sha256:"+"e"*64}},
        "incident_replay_refs": ["replay:1"],
        "replay_result": "PASS",
        "replay_exact_readback": True,
        "previous_failure_state": "CONTROLLER_WAIT",
        "first_state_beyond_failure": "UR.G2_EXECUTION_STARTED",
        "forward_progress_refs": ["progress:1"],
        "broader_regression_refs": ["regression:1"],
        "broader_regression_result": "PASS",
        "stale_dependent_state": [],
        "created_at": "2026-10-02T14:00:00Z",
        "created_by": {"type": "agent", "id": "dwa"},
    }
    d.update(overrides)
    return d


def _cert():
    return _m().certify_q0_runtime(**_cert_inputs())


def _acceptance(cert=None, **kwargs):
    m = _m()
    cert = cert or _cert()
    req = m.create_q0_acceptance_request(
        run_id=cert["run_id"], task_id=cert["task_id"],
        certified_q0_sha=cert["certified_q0_sha"],
        q0_certification_receipt_ref=cert["receipt_digest"],
        qualification_matrix_digest=cert["qualification_matrix_digest"],
        target_handoff="LOGIN_R00_PLUS",
        decision_authority={"type": "human", "id": "NHAT"},
        captured_via={"type": "direct_chat", "id": "default"},
        issued_at="2026-10-02T14:01:00Z", expires_at="2026-10-02T15:01:00Z",
    )
    receipt = m.decide_q0_acceptance(request=req, decision="ACCEPT", actor={"type": "human", "id": "NHAT"}, decided_at="2026-10-02T14:02:00Z", current_certified_q0_sha=cert["certified_q0_sha"], **kwargs)
    bundle = m.create_q0_accepted_handoff(certification=cert, acceptance=receipt, created_at="2026-10-02T14:03:00Z")
    bundle["acceptance_request"] = req
    return bundle


def test_q0_is_runtime_qualification_mode_not_normal_delivery_flow():
    profile = _m().q0_qualification_profile()
    assert profile["workflow_mode"] == "q0_live_qualification"
    assert profile["runtime_epoch"] == "UNIVERSAL_V2_DEVELOPMENT"
    assert profile["effect_authority_is_orthogonal"] is True
    assert profile["real_workload"] == "LOGIN_R00_PLUS"


def test_q0_real_workload_starts_only_after_campaign_ready_l3():
    m = _m()
    cert = _cert()
    accepted = _acceptance(cert)
    assert m.can_start_login_r00(certification=cert, acceptance=accepted) is True
    incomplete = dict(cert, certification_level="L2")
    with pytest.raises(m.Q0QualificationError, match="CAMPAIGN_NOT_READY_L3"):
        m.can_start_login_r00(certification=incomplete, acceptance=accepted)


def test_q0_acceptance_is_ur_g6_not_ur_g4():
    m = _m()
    assert m.Q0_ACCEPTANCE_GATE == "UR.G6"
    assert m.Q0_INTEGRATION_GATE == "UR.G4"


def test_ur_g2_completion_requires_execution_receipt_with_bound_digest():
    m = _m()
    with pytest.raises(m.Q0QualificationError, match="EXECUTION_EVIDENCE_REQUIRED"):
        m.complete_q0_gate(gate="UR.G2", evidence={})
    with pytest.raises(m.Q0QualificationError, match="EXECUTION_RECEIPT_INVALID"):
        m.complete_q0_gate(gate="UR.G2", evidence={"EXECUTION_RECEIPT": "exec:1"})
    receipt = _execution_receipt()
    assert m.complete_q0_gate(gate="UR.G2", evidence={"EXECUTION_RECEIPT": receipt})["gate_state"] == "PASSED"
    invalid_authority_receipt = _execution_receipt(authority_granted=True)
    with pytest.raises(m.Q0QualificationError, match="EXECUTION_RECEIPT_INVALID"):
        m.complete_q0_gate(gate="UR.G2", evidence={"EXECUTION_RECEIPT": invalid_authority_receipt})
    invalid_node_receipt = _execution_receipt(node_id="untrusted.node")
    with pytest.raises(m.Q0QualificationError, match="EXECUTION_RECEIPT_INVALID"):
        m.complete_q0_gate(gate="UR.G2", evidence={"EXECUTION_RECEIPT": invalid_node_receipt})


def test_ur_g2_execution_receipt_binds_exact_run_and_plan():
    m = _m()
    receipt = _execution_receipt()
    with pytest.raises(m.Q0QualificationError, match="EXECUTION_RECEIPT_RUN_MISMATCH"):
        m.complete_q0_gate(
            gate="UR.G2", evidence={"EXECUTION_RECEIPT": receipt},
            run_id="another-run", runtime_plan_digest=receipt["runtime_plan_digest"],
        )
    with pytest.raises(m.Q0QualificationError, match="EXECUTION_RECEIPT_PLAN_MISMATCH"):
        m.complete_q0_gate(
            gate="UR.G2", evidence={"EXECUTION_RECEIPT": receipt},
            run_id=receipt["run_id"], runtime_plan_digest="sha256:" + "f" * 64,
        )


def test_ur_g3_completion_requires_verification_receipt():
    m = _m()
    with pytest.raises(m.Q0QualificationError, match="VERIFICATION_RECEIPT_REQUIRED"):
        m.complete_q0_gate(gate="UR.G3", evidence={})
    assert m.complete_q0_gate(gate="UR.G3", evidence={"VERIFICATION_RECEIPT": "verify:1"})["gate_state"] == "PASSED"


def test_ur_g4_completion_requires_integration_receipt_or_explicit_integration_outcome():
    m = _m()
    with pytest.raises(m.Q0QualificationError, match="INTEGRATION_EVIDENCE_REQUIRED"):
        m.complete_q0_gate(gate="UR.G4", evidence={})
    for outcome in ("IN_PLACE", "NO_TRANSFER_REQUIRED", "DOMAIN_DEFINED"):
        assert m.complete_q0_gate(gate="UR.G4", evidence={"integration_outcome": outcome})["gate_state"] == "PASSED"
    assert m.complete_q0_gate(gate="UR.G4", evidence={"INTEGRATION_RECEIPT": "integrate:1"})["gate_state"] == "PASSED"


def test_ur_g5_completion_requires_target_validation_receipt():
    m = _m()
    with pytest.raises(m.Q0QualificationError, match="TARGET_VALIDATION_RECEIPT_REQUIRED"):
        m.complete_q0_gate(gate="UR.G5", evidence={})
    assert m.complete_q0_gate(gate="UR.G5", evidence={"TARGET_VALIDATION_RECEIPT": "target:1"})["gate_state"] == "PASSED"


def test_ur_g6_requires_q0_acceptance_and_handoff_receipts():
    m = _m()
    with pytest.raises(m.Q0QualificationError, match="Q0_ACCEPTANCE_RECEIPT_REQUIRED"):
        m.complete_q0_gate(gate="UR.G6", evidence={})
    m = _m()
    cert = _cert()
    accepted = _acceptance(cert)
    evidence = {"Q0_ACCEPTANCE_RECEIPT": accepted["acceptance"], "CLOSURE_RECEIPT": accepted["closure"], "HANDOFF_RECEIPT": accepted["handoff"]}
    result = m.complete_q0_gate(gate="UR.G6", evidence=evidence)
    assert result["gate_state"] == "PASSED"


def test_legacy_g4_merge_token_cannot_satisfy_ur_g4_integration():
    m = _m()
    with pytest.raises(m.Q0QualificationError, match="INTEGRATION_EVIDENCE_REQUIRED"):
        m.complete_q0_gate(gate="UR.G4", evidence={"G4_MERGE_TOKEN": "legacy-token"})


def test_legacy_g6_production_token_cannot_satisfy_q0_acceptance():
    m = _m()
    with pytest.raises(m.Q0QualificationError, match="Q0_ACCEPTANCE_RECEIPT_REQUIRED"):
        m.complete_q0_gate(gate="UR.G6", evidence={"G6_PRODUCTION_DATA_TOKEN": "legacy-token", "CLOSURE_RECEIPT": "close", "HANDOFF_RECEIPT": "handoff"})


def test_q0_acceptance_request_does_not_require_pr():
    request = _m().create_q0_acceptance_request(
        run_id="r", task_id="SCRUM-781", certified_q0_sha=_sha("a"),
        q0_certification_receipt_ref="sha256:"+"b"*64, qualification_matrix_digest="sha256:"+"a"*64,
        target_handoff="LOGIN_R00_PLUS", decision_authority={"type":"human","id":"NHAT"},
        captured_via={"type":"direct_chat","id":"default"}, issued_at="2026-10-02T14:00:00Z", expires_at="2026-10-02T15:00:00Z")
    assert "pr_number" not in request


def test_q0_acceptance_request_does_not_require_deployment():
    request = _m().create_q0_acceptance_request(
        run_id="r", task_id="SCRUM-781", certified_q0_sha=_sha("a"),
        q0_certification_receipt_ref="sha256:"+"b"*64, qualification_matrix_digest="sha256:"+"a"*64,
        target_handoff="LOGIN_R00_PLUS", decision_authority={"type":"human","id":"NHAT"},
        captured_via={"type":"direct_chat","id":"default"}, issued_at="2026-10-02T14:00:00Z", expires_at="2026-10-02T15:00:00Z")
    assert "environment" not in request
    assert request["effect_authority_granted"] is False


def test_nhat_is_human_decision_authority():
    request = _acceptance()
    assert request["acceptance"]["decision_authority"] == {"type":"human", "id":"NHAT"}


def test_approver_bot_is_transport_only():
    m = _m()
    req = m.create_q0_acceptance_request(
        run_id="r", task_id="SCRUM-781", certified_q0_sha=_sha("a"),
        q0_certification_receipt_ref="sha256:"+"b"*64, qualification_matrix_digest="sha256:"+"a"*64,
        target_handoff="LOGIN_R00_PLUS", decision_authority={"type":"human","id":"NHAT"},
        captured_via={"type":"approver_bot","id":"approver"}, issued_at="2026-10-02T14:00:00Z", expires_at="2026-10-02T15:00:00Z")
    assert req["decision_authority"]["id"] == "NHAT"
    assert req["captured_via"]["id"] == "approver"


def test_direct_nhat_acceptance_valid_without_approver_bot():
    cert = _cert()
    accepted = _acceptance(cert)
    assert accepted["acceptance"]["decision_authority"]["id"] == "NHAT"
    assert accepted["acceptance"]["captured_via"]["type"] == "direct_chat"


def test_q0_certification_binds_exact_certified_sha():
    cert = _cert()
    assert cert["candidate_sha"] == cert["certified_q0_sha"]
    assert cert["loaded_runtime_identity"] == cert["certified_q0_sha"]
    assert cert["certification_level"] == "L3"


def test_q0_certification_fails_on_runtime_identity_drift():
    m = _m()
    with pytest.raises(m.Q0QualificationError, match="RUNTIME_IDENTITY_DRIFT"):
        m.certify_q0_runtime(**_cert_inputs(loaded_runtime_identity=_sha("b")))


def test_q0_certification_fails_if_matrix_incomplete():
    m = _m()
    matrix = _matrix(); matrix["results"].pop("fresh_boot")
    body = {k:v for k,v in matrix.items() if k != "digest"}
    import hashlib
    matrix["digest"] = "sha256:" + hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    with pytest.raises(m.Q0QualificationError, match="QUALIFICATION_MATRIX_INCOMPLETE"):
        m.certify_q0_runtime(**_cert_inputs(qualification_matrix=matrix))


def test_q0_certification_fails_when_recursive_plan_dag_is_incomplete():
    m = _m()
    matrix = _matrix()
    matrix["results"]["recursive_plan_dag_complete"] = "FAIL"
    body = {k:v for k,v in matrix.items() if k != "digest"}
    import hashlib
    matrix["digest"] = "sha256:" + hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    with pytest.raises(m.Q0QualificationError) as error:
        m.certify_q0_runtime(**_cert_inputs(qualification_matrix=matrix))
    assert error.value.code == "QUALIFICATION_MATRIX_INCOMPLETE"


def test_q0_certification_fails_if_replay_does_not_advance_beyond_old_failure():
    m = _m()
    with pytest.raises(m.Q0QualificationError, match="FORWARD_PROGRESS_REQUIRED"):
        m.certify_q0_runtime(**_cert_inputs(first_state_beyond_failure="CONTROLLER_WAIT"))


def test_q0_acceptance_invalid_after_certified_sha_drift():
    m = _m()
    cert = _cert()
    req = m.create_q0_acceptance_request(
        run_id=cert["run_id"], task_id=cert["task_id"], certified_q0_sha=cert["certified_q0_sha"],
        q0_certification_receipt_ref=cert["receipt_digest"], qualification_matrix_digest=cert["qualification_matrix_digest"],
        target_handoff="LOGIN_R00_PLUS", decision_authority={"type":"human","id":"NHAT"},
        captured_via={"type":"direct_chat","id":"default"}, issued_at="2026-10-02T14:00:00Z", expires_at="2026-10-02T15:00:00Z")
    with pytest.raises(m.Q0QualificationError, match="CERTIFIED_SHA_MISMATCH"):
        m.decide_q0_acceptance(request=req, decision="ACCEPT", actor={"type":"human","id":"NHAT"}, decided_at="2026-10-02T14:02:00Z", current_certified_q0_sha=_sha("b"))


def test_q0_acceptance_single_consumption_idempotent():
    m = _m(); cert = _cert()
    req = m.create_q0_acceptance_request(
        run_id=cert["run_id"], task_id=cert["task_id"], certified_q0_sha=cert["certified_q0_sha"],
        q0_certification_receipt_ref=cert["receipt_digest"], qualification_matrix_digest=cert["qualification_matrix_digest"],
        target_handoff="LOGIN_R00_PLUS", decision_authority={"type":"human","id":"NHAT"},
        captured_via={"type":"direct_chat","id":"default"}, issued_at="2026-10-02T14:00:00Z", expires_at="2026-10-02T15:00:00Z")
    receipt = m.decide_q0_acceptance(request=req, decision="ACCEPT", actor={"type":"human","id":"NHAT"}, decided_at="2026-10-02T14:02:00Z", current_certified_q0_sha=cert["certified_q0_sha"])
    assert m.decide_q0_acceptance(request=req, decision="ACCEPT", actor={"type":"human","id":"NHAT"}, decided_at="2026-10-02T14:02:00Z", current_certified_q0_sha=cert["certified_q0_sha"], prior_receipt=receipt) == receipt
    with pytest.raises(m.Q0QualificationError, match="ACCEPTANCE_ALREADY_CONSUMED"):
        m.decide_q0_acceptance(request=req, decision="REJECT", actor={"type":"human","id":"NHAT"}, decided_at="2026-10-02T14:03:00Z", current_certified_q0_sha=cert["certified_q0_sha"], prior_receipt=receipt)


def test_continuation_uses_universal_kernel_lifecycle_not_counter_only_advance():
    m = _m()
    result = m.advance_qualification_gate(current_gate="UR.G4", current_state="ACTIVE", evidence={"INTEGRATION_RECEIPT":"ir:1"})
    assert result["next_gate"] == "UR.G5"
    assert result["next_state"] == "ACTIVE"
    assert result["sequence_delta"] == 1
    assert result["transition_receipt"]["artifact_type"] == "universal-lifecycle-execution-receipt"


def test_real_login_r00_cannot_start_before_q0_accepted_handoff():
    m = _m(); cert = _cert()
    with pytest.raises(m.Q0QualificationError, match="Q0_ACCEPTED_HANDOFF_REQUIRED"):
        m.can_start_login_r00(certification=cert, acceptance=None)
    accepted = _acceptance(cert)
    assert m.can_start_login_r00(certification=cert, acceptance=accepted) is True


def test_agent_host_compiles_q0_profile_node_without_legacy_registry_gate():
    from tools.node_architect import agent_runtime_entrypoint as host
    route = {
        "current_node": "q0.qualification-campaign", "gate": "UR.G2",
        "mode": "q0_live_qualification", "workflow_mode": "q0_live_qualification",
        "next_action": "q0_continue_universal_lifecycle", "next_gate": None,
        "instruction_digest": _m().q0_qualification_profile()["profile_digest"],
        "node_instruction_ref": "core/node-architect/node-instructions/q0/qualification-campaign.node-instruction.yaml",
        "implementation": {"kind":"python", "ref":"tools/node_architect/q0_qualification.py:resolve_q0_qualification_node"},
    }
    registry = host._q0_profile_implementation_registry(route, root=ROOT)
    assert registry["status"] == "PASS"
    assert len(registry["bindings"]) == 1
    binding = registry["bindings"][0]
    assert binding["node_id"] == "q0.qualification-campaign"
    assert binding["instruction_ref"] == "core/node-architect/node-instructions/q0/qualification-campaign.node-instruction.yaml"
    assert binding["authority_requirements"]["gate_authority_required"] is False
    assert binding["implementation_ref"].endswith(":resolve_q0_qualification_node")


def test_q0_e2e_campaign_certify_accept_handoff_then_login_start():
    m = _m()
    profile = m.q0_qualification_profile()
    assert profile["workflow_mode"] == "q0_live_qualification"
    for gate, evidence in (
        ("UR.G0", {"UNDERSTANDING_RECEIPT":"g0"}),
        ("UR.G1", {"PLAN_RECEIPT":"g1"}),
        ("UR.G2", {"EXECUTION_RECEIPT": _execution_receipt()}),
        ("UR.G3", {"VERIFICATION_RECEIPT":"g3"}),
        ("UR.G4", {"integration_outcome":"IN_PLACE"}),
        ("UR.G5", {"TARGET_VALIDATION_RECEIPT":"g5"}),
    ):
        assert m.complete_q0_gate(gate=gate, evidence=evidence)["gate_state"] == "PASSED"
    cert = _cert()
    bundle = _acceptance(cert)
    assert bundle["status"] == "Q0_ACCEPTED_AUTONOMOUS_HANDOFF"
    assert m.can_start_login_r00(certification=cert, acceptance=bundle) is True


def test_q0_certification_fails_if_load_proof_lacks_process_identity():
    m = _m()
    evidence = dict(_cert_inputs()["load_proof_evidence"])
    evidence.pop("runtime_process_id")
    with pytest.raises(m.Q0QualificationError, match="LOAD_PROOF_PROCESS_IDENTITY_REQUIRED"):
        m.certify_q0_runtime(**_cert_inputs(load_proof_evidence=evidence))


def test_q0_load_proof_must_bind_exact_candidate_sha():
    m = _m()
    with pytest.raises(m.Q0QualificationError, match="LOAD_PROOF_IDENTITY_MISMATCH"):
        m.certify_q0_runtime(**_cert_inputs(load_proof_evidence={"activation_id":"act-1", "candidate_sha":_sha("a"), "loaded_source_sha":_sha("b"), "source_root":"worktree:q0", "runtime_session_id":"20260923_175734_bea63d", "runtime_process_id":"runtime:test-1", "loaded_profile_digest":_m().q0_qualification_profile()["profile_digest"], "loaded_module_identities":{"tools/node_architect/q0_qualification.py":"sha256:"+"e"*64}}))


def test_q0_runtime_defect_self_repairs_without_falling_back_to_legacy_flow():
    profile = _m().q0_qualification_profile()
    assert profile["defect_route"] == "GWC_RUNTIME_DEFECT_SELF_REMEDIATION"
    assert profile["legacy_fallback"] is False
    assert profile["legacy_effect_gates_define_lifecycle"] is False


def test_native_q0_profile_is_digest_bound_and_schema_valid():
    import hashlib
    import jsonschema
    profile = _m().q0_qualification_profile()
    stored = json.loads((ROOT / "core/node-architect/q0-live-qualification-profile.json").read_text())
    schema = json.loads((ROOT / "schemas/q0-live-qualification-profile.schema.json").read_text())
    jsonschema.validate(stored, schema)
    assert stored == profile
    body = {k:v for k,v in profile.items() if k != "profile_digest"}
    digest = "sha256:" + hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    assert profile["profile_digest"] == digest


def test_q0_mode_routes_without_legacy_g2_envelope_for_read_only_probe():
    m = _m()
    context = {"workflow_mode":"q0_live_qualification", "runtime_epoch":"UNIVERSAL_V2_DEVELOPMENT",
               "task_id":"SCRUM-781", "run_id":"scrum781-q0-20260920T074727Z",
               "gate":"UR.G2", "requested_action":"run_probe", "effect_class":"read_only",
               "q0_profile":m.q0_qualification_profile()}
    result = m.validate_q0_route_context(context)
    assert result["permitted"] is True
    assert result["authority_granted"] is False


def test_q0_branch_effect_requires_separate_exact_authority():
    m = _m()
    context = {"workflow_mode":"q0_live_qualification", "runtime_epoch":"UNIVERSAL_V2_DEVELOPMENT",
               "task_id":"SCRUM-781", "run_id":"scrum781-q0-20260920T074727Z",
               "gate":"UR.G2", "requested_action":"modify_q0_code", "effect_class":"branch_local_write",
               "q0_profile":m.q0_qualification_profile()}
    assert m.validate_q0_route_context(context)["reason_code"] == "Q0_EFFECT_AUTHORITY_REQUIRED"
    context["q0_effect_authority_decision"] = {"status":"AUTHORIZED", "task_id":"SCRUM-781",
        "run_id":context["run_id"], "action":"modify_q0_code", "branch":"fix/SCRUM-781-q0-canonical",
        "runtime_epoch":"UNIVERSAL_V2_DEVELOPMENT"}
    assert m.validate_q0_route_context(context)["permitted"] is True
    context["effect_class"] = "external_effect"
    assert m.validate_q0_route_context(context)["reason_code"] == "Q0_EXTERNAL_EFFECT_OUT_OF_SCOPE"


def test_q0_legacy_approval_token_gates_remain_effect_only():
    from tools.node_architect.approval_token_generation import VALID_GATES
    assert VALID_GATES == {"G2_EXECUTION", "G4_MERGE", "G5_DEPLOY", "G6_PRODUCTION_DATA"}
    assert "UR.G4" not in VALID_GATES and "UR.G6" not in VALID_GATES


def test_q0_acceptance_and_certification_schemas_validate_native_receipts():
    import jsonschema
    m = _m(); cert = _cert()
    cert_schema = json.loads((ROOT / "schemas/q0-certification-receipt.schema.json").read_text())
    request_schema = json.loads((ROOT / "schemas/q0-acceptance-request.schema.json").read_text())
    decision_schema = json.loads((ROOT / "schemas/q0-acceptance-decision-receipt.schema.json").read_text())
    handoff_schema = json.loads((ROOT / "schemas/q0-handoff-receipt.schema.json").read_text())
    closure_schema = json.loads((ROOT / "schemas/q0-closure-receipt.schema.json").read_text())
    jsonschema.validate(cert, cert_schema)
    bundle = _acceptance(cert)
    jsonschema.validate(bundle["acceptance"], decision_schema)
    jsonschema.validate(bundle["acceptance_request"], request_schema)
    jsonschema.validate(bundle["closure"], closure_schema)
    jsonschema.validate(bundle["handoff"], handoff_schema)
