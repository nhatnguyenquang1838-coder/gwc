"""The active bridge is a V2-only, fail-closed projection boundary."""
from __future__ import annotations

import pytest

from tools.node_architect.live_runtime_bridge import (
    GATES,
    build_live_runtime_event,
    dispatch_live_runtime_event,
    resume_live_runtime_event,
)
from tools.node_architect.q0_qualification import Q0_RUNTIME_EPOCH, Q0_WORKFLOW_MODE, q0_qualification_profile


def _state():
    return {
        "task_id": "SCRUM-781",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "branch": "fix/SCRUM-781-q0-canonical",
        "base_sha": "414002f92d48083e7133236346b26e3a2a047e33",
        "head_sha": "6e753f48344918d9141f9721a005695f2b4a9bea",
        "scope_hash": "sha256:" + "c" * 64,
        "source_kind": "canonical_agent_gate_state",
    }


def _event(gate="UR.G2"):
    return build_live_runtime_event(
        canonical_state=_state(),
        event_id=f"bridge-{gate}",
        run_id="scrum781-q0-20260920T074727Z",
        gate=gate,
        requested_action="q0_execute_probe",
        scenario="q0_live_qualification",
        input_payload={
            "workflow_mode": Q0_WORKFLOW_MODE,
            "runtime_epoch": Q0_RUNTIME_EPOCH,
            "q0_profile": q0_qualification_profile(),
        },
    )


def test_active_bridge_accepts_only_ur_namespaced_v2_events():
    assert GATES == tuple(f"UR.G{index}" for index in range(7))
    for gate in GATES:
        event = _event(gate)
        assert event["schema_id"] == "gwc.universal-run.live-runtime-event.v2"
        assert event["schema_version"] == 2
        assert event["gate"] == gate
        assert event["workflow_mode"] == Q0_WORKFLOW_MODE
        assert event["runtime_epoch"] == Q0_RUNTIME_EPOCH
        assert event["authority_granted"] is False
        assert event["executed_effects"] == []
        assert "typed_next" not in event


def test_active_bridge_rejects_legacy_gate_and_mismatched_q0_binding():
    base = {
        "canonical_state": _state(),
        "event_id": "negative-bridge-event",
        "run_id": "scrum781-q0-20260920T074727Z",
        "requested_action": "q0_execute_probe",
        "scenario": "q0_live_qualification",
        "input_payload": {
            "workflow_mode": Q0_WORKFLOW_MODE,
            "runtime_epoch": Q0_RUNTIME_EPOCH,
            "q0_profile": q0_qualification_profile(),
        },
    }
    with pytest.raises(ValueError, match="UNIVERSAL_GATE_INVALID"):
        build_live_runtime_event(**base, gate="G0_CONTEXT")
    with pytest.raises(ValueError, match="GWC_RUNTIME_DEFECT"):
        build_live_runtime_event(
            **{**base, "gate": "UR.G0", "input_payload": {**base["input_payload"], "runtime_epoch": "UNIVERSAL_V1"}}
        )


def test_bridge_projection_never_executes_or_advances_controller_state():
    result = dispatch_live_runtime_event(event=_event("UR.G2"))

    assert result == {
        "status": "BLOCKED",
        "reason_code": "USE_UNIVERSAL_V2_EXECUTOR",
        "authority_granted": False,
        "executed_effects": [],
    }
    resumed = resume_live_runtime_event(checkpoint={"run_state": {"active_gate": "UR.G2"}})
    assert resumed["status"] == "BLOCKED"
    assert resumed["reason_code"] == "USE_UNIVERSAL_V2_CONTROLLER"
