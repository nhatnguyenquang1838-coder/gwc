"""Real native coverage for q0_qualification functions that previously had
zero test coverage: verify_q0_verification_receipt and verify_q0_certification.

These drive the actual module functions with real sealed receipts. They are
native engineering tests; they never claim LOAD_PROOF, original replay, L3, or
a native gate receipt.
"""
from __future__ import annotations

import hashlib
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


def _digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _execution_receipt():
    m = _m()
    q0_profile = m.q0_qualification_profile()
    node_id = q0_profile["qualification_nodes"]["UR.G2"]["node_id"]
    run_id = "scrum781-q0-native-verify-1"
    body = {
        "schema_id": "gwc.universal-run.executor-action-receipt.v2",
        "schema_version": 2,
        "artifact_type": "executor-action-receipt",
        "runtime_protocol": "gwc.universal.controller/v2",
        "run_id": run_id,
        "runtime_epoch": "UNIVERSAL_V2_DEVELOPMENT",
        "runtime_profile_digest": m.load_universal_v2_default_profile()["profile_digest"],
        "route_id": "UNIVERSAL_RUN_NEW_RUNTIME",
        "runtime_plan_digest": "sha256:" + "a" * 64,
        "node_allocation_id": f"{run_id}:{node_id}",
        "node_id": node_id,
        "gate": "UR.G2",
        "action": "q0_execute_probe",
        "sequence": 3,
        "assignment_digest": "sha256:" + "c" * 64,
        "event_id": "q0-native-verify-event",
        "host_status": "ACTION_COMPLETE",
        "host_result_digest": "sha256:" + "b" * 64,
        "evidence_refs": {"node-result": ".gwc/node-result.json"},
        "authority_granted": False,
        "executed_effects": [],
    }
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return {**body, "receipt_digest": "sha256:" + hashlib.sha256(raw).hexdigest()}


def _g3_transition_receipt(g2):
    m = _m()
    body = {
        "schema_id": "gwc.universal-run.controller-transition-receipt.v2",
        "schema_version": 2,
        "run_id": g2["run_id"],
        "runtime_plan_digest": g2["runtime_plan_digest"],
        "candidate_sha": _sha("a"),
        "from_gate": "UR.G2",
        "to_gate": "UR.G3",
        "consumed_receipt_digest": g2["receipt_digest"],
        "idempotency_key": g2["event_id"],
        "transition_ref": "q0-native-verify/transition.json",
        "pre_state": {"sequence": 8, "state_digest": "sha256:" + "1" * 64},
        "post_state": {"sequence": 9, "state_digest": "sha256:" + "2" * 64},
        "authority_granted": False,
        "executed_effects": [],
        "kernel_completion_receipt": {"action": "COMPLETE", "result": "PASS"},
        "kernel_transition_receipt": {"action": "ADVANCE", "result": "PASS"},
    }
    return {**body, "transition_digest": m._digest(body)}


def _verification_receipt():
    m = _m()
    g2 = _execution_receipt()
    g2_bytes = (json.dumps(g2, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    return m.create_q0_verification_receipt(
        run_id=g2["run_id"],
        runtime_plan_digest=g2["runtime_plan_digest"],
        candidate_sha=_sha("a"),
        g2_execution_receipt=g2,
        g2_execution_receipt_ref="q0-native-verify/executor-receipts/executor-action-receipt.json",
        g2_execution_receipt_bytes=g2_bytes,
        controller_transition_receipt=_g3_transition_receipt(g2),
        v2_isolation_evidence={
            "candidate_sha": _sha("a"),
            "result": "UNIVERSAL_V2_CORE_ISOLATED_GWC_V1_QUARANTINED",
            "evidence_ref": "q0-native-verify/e56-isolation-handoff-evidence.json",
            "evidence_sha256": "c" * 64,
        },
        v1_quarantine_evidence={
            "manifest_ref": "legacy/gwc-v1/runtime-quarantine-manifest.json",
            "manifest_sha256": "d" * 64,
            "archived_sources_verified": 16,
            "fallback_forbidden": True,
        },
        regression_evidence={
            "candidate_sha": _sha("a"),
            "command": "python -m pytest tests/test_universal_v2_core_isolation.py -q",
            "exit_code": 0,
            "tests_passed": 327,
            "result_sha256": "e" * 64,
        },
        created_at="2026-10-03T00:00:00Z",
    )


def _cert_inputs(**overrides):
    m = _m()
    matrix_body = {
        "mandatory_entries": list(m.MANDATORY_QUALIFICATION_ENTRIES),
        "results": {k: "PASS" for k in m.MANDATORY_QUALIFICATION_ENTRIES},
        "active_unresolved_defects": [],
    }
    matrix = {"digest": _digest(matrix_body), **matrix_body}
    d = {
        "run_id": "scrum781-q0-native-verify-1",
        "task_id": "SCRUM-781",
        "runtime_epoch": "UNIVERSAL_V2_DEVELOPMENT",
        "qualification_profile": "q0_live_qualification",
        "qualification_profile_digest": m.q0_qualification_profile()["profile_digest"],
        "qualification_matrix": matrix,
        "candidate_sha": _sha("a"),
        "loaded_runtime_identity": _sha("a"),
        "load_proof_ref": "load-proof:1",
        "load_proof_evidence": {
            "activation_id": "act-1", "candidate_sha": _sha("a"),
            "loaded_source_sha": _sha("a"), "source_root": "worktree:q0",
            "runtime_session_id": "20260923_175734_bea63d",
            "runtime_process_id": "runtime:test-1",
            "loaded_profile_digest": m.q0_qualification_profile()["profile_digest"],
            "loaded_module_identities": {"tools/node_architect/q0_qualification.py": "sha256:" + "e" * 64},
        },
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


# --- verify_q0_verification_receipt -----------------------------------------
def test_verify_q0_verification_receipt_accepts_real_sealed_receipt():
    m = _m()
    receipt = _verification_receipt()
    assert m.verify_q0_verification_receipt(receipt) is True
    # Exact runtime binding is honored.
    assert m.verify_q0_verification_receipt(
        receipt, run_id=receipt["run_id"],
        runtime_plan_digest=receipt["runtime_plan_digest"],
        candidate_sha=receipt["candidate_sha"],
    ) is True


def test_verify_q0_verification_receipt_rejects_run_mismatch():
    m = _m()
    receipt = _verification_receipt()
    with pytest.raises(m.Q0QualificationError, match="VERIFICATION_RECEIPT_RUN_MISMATCH"):
        m.verify_q0_verification_receipt(receipt, run_id="other-run")


def test_verify_q0_verification_receipt_rejects_tampered_seal():
    m = _m()
    receipt = _verification_receipt()
    receipt["result"] = "FAIL"  # breaks the schema const + seal invariant
    with pytest.raises(m.Q0QualificationError, match="VERIFICATION_RECEIPT_INVALID"):
        m.verify_q0_verification_receipt(receipt)


def test_verify_q0_verification_receipt_rejects_effect_boundary_violation():
    m = _m()
    receipt = _verification_receipt()
    receipt["authority_granted"] = True  # schema const False rejects first
    with pytest.raises(m.Q0QualificationError, match="VERIFICATION_RECEIPT_INVALID"):
        m.verify_q0_verification_receipt(receipt)


# --- verify_q0_certification -------------------------------------------------
def test_verify_q0_certification_accepts_real_certificate():
    m = _m()
    cert = m.certify_q0_runtime(**_cert_inputs())
    assert m.verify_q0_certification(cert) is True


def test_verify_q0_certification_rejects_tampered_certificate():
    m = _m()
    cert = m.certify_q0_runtime(**_cert_inputs())
    cert["certification_level"] = "L2"
    assert m.verify_q0_certification(cert) is False


def test_verify_q0_certification_rejects_identity_drift():
    m = _m()
    cert = m.certify_q0_runtime(**_cert_inputs())
    cert["certified_q0_sha"] = _sha("b")  # drifts from candidate_sha
    assert m.verify_q0_certification(cert) is False
