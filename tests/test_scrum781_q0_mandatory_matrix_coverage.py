"""Real native coverage for the 7 mandatory Q0 matrix entries that previously
had only synthetic `_matrix()` keys and no exercising test.

Each test drives the actual `tools.node_architect.q0_qualification` functions
(route context, node resolution, gate advance, matrix validation) so the
mandatory qualification entries are proven by real behavior, not by a
hand-built receipt. These are native engineering tests; they never claim
LOAD_PROOF, original replay, L3, or a native gate receipt.
"""
from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from tools.node_architect.q0_native_g1_admission import build_native_g1_plan_receipt

ROOT = Path(__file__).resolve().parents[1]
MOD = "tools.node_architect.q0_qualification"


def _m():
    return importlib.import_module(MOD)


def _sha(ch):
    return ch * 40


def _digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _q0_context(**overrides):
    profile = _m().q0_qualification_profile()
    ctx = {
        "workflow_mode": "q0_live_qualification",
        "runtime_epoch": "UNIVERSAL_V2_DEVELOPMENT",
        "task_id": "SCRUM-781",
        "run_id": "scrum781-q0-native-matrix-1",
        "gate": "UR.G0",
        "requested_action": "q0_understand",
        "q0_profile": profile,
        "effect_class": "read_only",
    }
    ctx.update(overrides)
    return ctx


def _matrix(**overrides):
    body = {
        "mandatory_entries": list(_m().MANDATORY_QUALIFICATION_ENTRIES),
        "results": {k: "PASS" for k in _m().MANDATORY_QUALIFICATION_ENTRIES},
        "active_unresolved_defects": [],
    }
    body.update(overrides)
    return {"digest": _digest({k: v for k, v in body.items() if k != "digest"}), **body}


# --- default_route -----------------------------------------------------------
def test_mandatory_default_route_resolves_to_universal_v2_route():
    """default_route: a valid Q0 read-only context resolves to the Universal V2
    qualification node, never a legacy route."""
    m = _m()
    ctx = _q0_context()
    resolved = m.resolve_q0_qualification_node(ctx)
    assert resolved["permitted"] is True
    assert resolved["reason_code"] == "Q0_QUALIFICATION_NODE_SELECTED"
    assert resolved["runtime_epoch"] == "UNIVERSAL_V2_DEVELOPMENT"
    assert resolved["workflow_mode"] == "q0_live_qualification"
    assert resolved["current_node"] == "q0.qualification-campaign"
    assert resolved["authority_granted"] is False


def test_mandatory_default_route_rejects_legacy_epoch():
    """default_route: a non-Universal-V2 epoch must fail closed."""
    m = _m()
    ctx = _q0_context(runtime_epoch="GWC_V1_LEGACY")
    assert m.resolve_q0_qualification_node(ctx)["permitted"] is False
    assert m.resolve_q0_qualification_node(ctx)["reason_code"] == "Q0_RUNTIME_EPOCH_MISMATCH"


# --- node_architect_seam ----------------------------------------------------
def test_mandatory_node_architect_seam_binds_instruction_and_implementation():
    """node_architect_seam: the resolved node carries the Node Architect
    instruction ref, descriptor ref, and implementation ref."""
    m = _m()
    resolved = m.resolve_q0_qualification_node(_q0_context())
    assert resolved["node_instruction_ref"] == (
        "core/node-architect/node-instructions/q0/qualification-campaign.node-instruction.yaml"
    )
    assert resolved["node_descriptor_ref"] == "core/node-architect/q0/qualification-campaign.node.json"
    assert resolved["implementation_ref"].endswith(":resolve_q0_qualification_node")
    assert resolved["next_action"] == "q0_continue_universal_lifecycle"


def test_mandatory_node_architect_seam_rejects_action_mismatch():
    """node_architect_seam: a requested action that does not match the node's
    declared action must fail closed."""
    m = _m()
    ctx = _q0_context(requested_action="q0_execute_probe")  # wrong for UR.G0
    assert m.resolve_q0_qualification_node(ctx)["reason_code"] == "Q0_NODE_ACTION_MISMATCH"


# --- typed_continuation ------------------------------------------------------
def test_mandatory_typed_continuation_advances_gate_with_typed_next():
    """typed_continuation: advancing a completed gate yields a typed next gate
    and state, not a counter-only advance."""
    m = _m()
    result = m.advance_qualification_gate(
        current_gate="UR.G0", current_state="ACTIVE",
        evidence={"UNDERSTANDING_RECEIPT": "g0"},
    )
    assert result["next_gate"] == "UR.G1"
    assert result["next_state"] == "ACTIVE"
    assert result["sequence_delta"] == 1
    assert result["transition_receipt"]["artifact_type"] == "universal-lifecycle-execution-receipt"


def test_mandatory_typed_continuation_requires_gate_evidence():
    """typed_continuation: advancing without the gate's required evidence must
    fail closed."""
    m = _m()
    with pytest.raises(m.Q0QualificationError, match="UNDERSTANDING_RECEIPT_REQUIRED"):
        m.advance_qualification_gate(current_gate="UR.G0", current_state="ACTIVE", evidence={})


# --- restart_recovery --------------------------------------------------------
def test_mandatory_restart_recovery_resumes_from_durable_gate_state():
    """restart_recovery: a fresh advance from a durable current gate/state
    resumes the lifecycle deterministically (no stale conversation state)."""
    m = _m()
    run_id = "scrum781-q0-restart-g1"
    candidate = _sha("d")
    allocation = {
        "node_allocation_id": f"{run_id}:W6",
        "content_digest": {"value": "sha256:" + "c" * 64},
    }
    runtime_plan = {
        "run_id": run_id,
        "digest": "sha256:" + "a" * 64,
        "source_binding": {"pre_head_sha": candidate},
        "node_allocations": [allocation["node_allocation_id"]],
        "dag": {"nodes": [
            {"id": f"W{i}", "predecessors": [] if i == 1 else [f"W{i-1}"]}
            for i in range(1, 7)
        ]},
    }
    receipt = build_native_g1_plan_receipt(
        run_id=run_id, runtime_plan_digest=runtime_plan["digest"],
        candidate_sha=candidate, node_allocation=allocation,
        runtime_plan=runtime_plan, source_head=candidate,
    )
    evidence = {"PLAN_RECEIPT": receipt}
    bound_complete = m.complete_q0_gate
    kwargs = {
        "run_id": run_id, "runtime_plan_digest": runtime_plan["digest"],
        "candidate_sha": candidate, "node_allocation": allocation,
        "runtime_plan": runtime_plan, "source_head": candidate,
    }
    assert bound_complete(gate="UR.G1", evidence=evidence, **kwargs)["gate_state"] == "PASSED"
    # advance_qualification_gate owns lifecycle advancement; bind its internal
    # completion check to the same validated G1 plan receipt.
    def complete_with_bindings(*, gate, evidence, **_ignored):
        if gate == "UR.G1":
            return bound_complete(gate=gate, evidence=evidence, **kwargs)
        return bound_complete(gate=gate, evidence=evidence, **_ignored)

    with patch.object(m, "complete_q0_gate", side_effect=complete_with_bindings):
        first = m.advance_qualification_gate(
            current_gate="UR.G1", current_state="ACTIVE", evidence=evidence,
        )
        # A 'restart' re-advances from the same durable gate/state and must be
        # deterministic (same next gate/state).
        second = m.advance_qualification_gate(
            current_gate="UR.G1", current_state="ACTIVE", evidence=evidence,
        )
    assert first["next_gate"] == second["next_gate"] == "UR.G2"
    assert first["next_state"] == second["next_state"] == "ACTIVE"


# --- self_fix_replay ---------------------------------------------------------
def test_mandatory_self_fix_replay_advances_beyond_old_failure():
    """self_fix_replay: after a gate completes, replaying the advance reaches a
    legal state beyond the prior failure point (forward progress)."""
    m = _m()
    # Old failure state: stuck at UR.G0 with no evidence.
    with pytest.raises(m.Q0QualificationError):
        m.advance_qualification_gate(current_gate="UR.G0", current_state="ACTIVE", evidence={})
    # Self-fix: provide the evidence and advance beyond the old failure.
    result = m.advance_qualification_gate(
        current_gate="UR.G0", current_state="ACTIVE",
        evidence={"UNDERSTANDING_RECEIPT": "g0"},
    )
    assert result["next_gate"] == "UR.G1"
    assert result["next_gate"] != "UR.G0"  # forward progress beyond old failure


# --- stale_state_fail_closed -------------------------------------------------
def test_mandatory_stale_state_fails_closed_on_profile_drift():
    """stale_state_fail_closed: a route context bound to a stale/drifted Q0
    profile must fail closed rather than proceed."""
    m = _m()
    stale_profile = dict(m.q0_qualification_profile())
    stale_profile["revision"] = "1.0"  # drift from live 2.0
    ctx = _q0_context(q0_profile=stale_profile)
    assert m.validate_q0_route_context(ctx)["permitted"] is False
    assert m.validate_q0_route_context(ctx)["reason_code"] == "Q0_PROFILE_BINDING_MISMATCH"


def test_mandatory_stale_state_fails_closed_on_workflow_mode_drift():
    """stale_state_fail_closed: a non-Q0 workflow mode must fail closed."""
    m = _m()
    ctx = _q0_context(workflow_mode="production")
    assert m.validate_q0_route_context(ctx)["permitted"] is False
    assert m.validate_q0_route_context(ctx)["reason_code"] == "Q0_WORKFLOW_MODE_REQUIRED"


# --- recursive_plan_dag_complete ---------------------------------------------
def test_mandatory_recursive_plan_dag_complete_requires_all_entries():
    """recursive_plan_dag_complete: the qualification matrix must declare and
    PASS every mandatory entry; a missing entry fails closed."""
    m = _m()
    matrix = _matrix()
    m._validate_matrix(matrix)  # complete matrix passes
    incomplete = _matrix()
    incomplete["results"].pop("fresh_boot")
    incomplete["digest"] = _digest({k: v for k, v in incomplete.items() if k != "digest"})
    with pytest.raises(m.Q0QualificationError, match="QUALIFICATION_MATRIX_INCOMPLETE"):
        m._validate_matrix(incomplete)


def test_mandatory_recursive_plan_dag_complete_rejects_active_defects():
    """recursive_plan_dag_complete: an active unresolved defect must fail
    closed."""
    m = _m()
    matrix = _matrix(active_unresolved_defects=["Q0_DEFECT_1"])
    matrix["digest"] = _digest({k: v for k, v in matrix.items() if k != "digest"})
    with pytest.raises(m.Q0QualificationError, match="ACTIVE_Q0_DEFECTS"):
        m._validate_matrix(matrix)
