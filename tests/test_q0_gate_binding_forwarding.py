"""Regression probes for Q0 gate bindings; synthetic fixtures, not live receipts."""
from __future__ import annotations

import copy

import pytest

from tools.node_architect.q0_native_g1_admission import build_native_g1_plan_receipt
from tools.node_architect.q0_qualification import (
    Q0QualificationError,
    advance_qualification_gate,
    complete_q0_gate,
)


def _bindings():
    run_id = "unit-q0-g1-forwarding"
    candidate = "b" * 40
    allocation = {
        "node_allocation_id": f"{run_id}:W6",
        "content_digest": {"value": "sha256:" + "c" * 64},
    }
    plan = {
        "run_id": run_id,
        "digest": "sha256:" + "a" * 64,
        "source_binding": {"pre_head_sha": candidate},
        "node_allocations": [allocation["node_allocation_id"]],
        "dag": {"nodes": [
            {"id": f"W{i}", "predecessors": [] if i == 1 else [f"W{i-1}"]}
            for i in range(1, 7)
        ]},
    }
    return {
        "run_id": run_id, "runtime_plan_digest": plan["digest"],
        "candidate_sha": candidate, "source_head": candidate,
        "runtime_plan": plan, "node_allocation": allocation,
    }


def test_g1_advance_accepts_same_bindings_as_completion_without_mock():
    bindings = _bindings()
    receipt = build_native_g1_plan_receipt(**bindings)
    evidence = {"PLAN_RECEIPT": receipt}
    assert complete_q0_gate(gate="UR.G1", evidence=evidence, **bindings)["gate_state"] == "PASSED"
    transition = advance_qualification_gate(
        current_gate="UR.G1", current_state="ACTIVE", evidence=evidence, **bindings,
    )
    assert transition["next_gate"] == "UR.G2"
    assert transition["next_state"] == "ACTIVE"
    assert receipt["authority_granted"] is False
    assert receipt["consumed"] is False


@pytest.mark.parametrize("field", ["node_allocation", "runtime_plan", "source_head"])
def test_g1_advance_rejects_drift_without_mutating_input(field):
    bindings = _bindings()
    receipt = build_native_g1_plan_receipt(**bindings)
    original = copy.deepcopy(receipt)
    if field == "node_allocation":
        bindings[field]["node_allocation_id"] = "other-allocation"
    elif field == "runtime_plan":
        bindings[field]["digest"] = "sha256:" + "d" * 64
    else:
        bindings[field] = "d" * 40
    with pytest.raises(Q0QualificationError, match="PLAN_RECEIPT_INVALID"):
        advance_qualification_gate(
            current_gate="UR.G1", current_state="ACTIVE",
            evidence={"PLAN_RECEIPT": receipt}, **bindings,
        )
    assert receipt == original


def test_controller_g1_completes_with_canonical_producer_allocation():
    import hashlib
    import json
    import runpy
    from pathlib import Path

    from tools.node_architect.universal_run_controller import UniversalController

    fixture = runpy.run_path(str(Path(__file__).with_name("test_universal_v2_core_isolation.py")))
    profile, plan, state, allocation = fixture["_make_v2_binding"]()
    plan["dag"] = {"nodes": [
        {"id": f"W{i}", "predecessors": [] if i == 1 else [f"W{i-1}"]}
        for i in range(1, 7)
    ]}

    def seal(value, field):
        value.pop(field, None)
        value[field] = "sha256:" + hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest()

    seal(plan, "digest")
    state.update(active_gate="UR.G1", next_owner="CONTROLLER",
                 typed_next="CONTINUE_UNIVERSAL_LANE_REMEDIATION", evidence_gap=["PLAN_RECEIPT"])
    state["execution_refs"]["runtime_plan_digest"] = plan["digest"]
    seal(state, "state_digest")
    controller = UniversalController(
        profile=profile, runtime_plan=plan, run_state=state, node_allocation=allocation,
    )
    assert controller.assign_current_action()["actor"] == "CONTROLLER"
    candidate = plan["source_binding"]["pre_head_sha"]
    receipt = build_native_g1_plan_receipt(
        run_id=plan["run_id"], runtime_plan_digest=plan["digest"], candidate_sha=candidate,
        node_allocation=allocation, runtime_plan=plan, source_head=candidate,
    )
    decision = controller.complete_controller_owned_gate(evidence={"PLAN_RECEIPT": receipt})
    assert decision["successor_run_state"]["active_gate"] == "UR.G2"
    assert decision["authority_granted"] is False
    assert decision["executed_effects"] == []
