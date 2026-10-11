"""SCRUM-781: live Agent Host must accept Universal Runtime v2 gates."""
from tools.node_architect.live_runtime_bridge import (
    GATES, LiveRuntimeState, build_live_runtime_event, dispatch_live_runtime_event,
)

STATE = {
    "task_id": "SCRUM-781",
    "repository": "nhatnguyenquang1838-coder/gwc",
    "branch": "fix/SCRUM-781-node-direct-mode-regression-20261010",
    "base_sha": "a" * 40,
    "head_sha": "b" * 40,
    "scope_hash": "sha256:" + "c" * 64,
    "source_kind": "canonical_agent_gate_state",
    "profile_revision": "profile-v2",
    "graph_revision": "graph-v2",
    "node_registry_revision": "registry-v2",
    "policy_revision": "policy-v2",
}

def event(gate: str) -> dict:
    return build_live_runtime_event(
        canonical_state=STATE, event_id=f"scrum781-{gate}", run_id="scrum781-gate-fixture",
        gate=gate, requested_action="observe", scenario="standard_pr_delivery",
        input_payload={"gate_context": {"gate": gate}},
    )

def test_universal_v2_canonical_gate_event_building():
    for n in range(7):
        gate = f"UR.G{n}"
        assert gate in GATES
        result = event(gate)
        assert result["gate"] == gate
        assert result["live_agent_event"] is True
        assert result["synthetic"] is False
        assert result["source_kind"] == "canonical_agent_gate_state"

def test_short_g0_g6_aliases_are_canonicalized_not_downgraded():
    for n in range(7):
        result = event(f"G{n}")
        assert result["gate"] == f"UR.G{n}"

def test_legacy_gate_names_remain_explicit_compatibility():
    assert event("G0_CONTEXT")["gate"] == "G0_CONTEXT"
    assert event("G6_PRODUCTION_DATA")["gate"] == "G6_PRODUCTION_DATA"

def test_universal_gates_reach_live_dispatch_without_legacy_gate_rejection(tmp_path):
    for n in range(7):
        result = dispatch_live_runtime_event(
            event=event(f"UR.G{n}"),
            route_decision={},
            implementation_registry={"bindings": []},
            mode="shadow_readonly", semantic_handlers={}, capability_handlers={},
            readback_handler=lambda *a, **k: {"status": "VERIFIED"},
            evidence_root=tmp_path, state=LiveRuntimeState(),
            applicability_decision={"decision": "NOT_APPLICABLE", "policy_ref": "test-v2",
                                    "decision_digest": "sha256:" + "f" * 64},
        )
        assert result["status"] == "LIVE_GATE_NOT_APPLICABLE"
        assert result["authority_granted"] is False
        assert result["executed_effects"] == []

def test_unknown_gate_still_rejected():
    try:
        event("UR.G7")
    except ValueError as err:
        assert str(err) == "unsupported gate"
    else:
        raise AssertionError("unsupported gate accepted")
