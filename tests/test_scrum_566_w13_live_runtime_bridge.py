from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

GATES = ("G0_CONTEXT", "G1_ALIGNMENT", "G2_EXECUTION", "G3_PR", "G4_MERGE", "G5_DEPLOY", "G6_PRODUCTION_DATA")


def _module(name: str):
    spec = importlib.util.find_spec(name)
    assert spec is not None, f"{name} must exist"
    return importlib.import_module(name)


def _state(**overrides) -> dict:
    value = {
        "task_id": "SCRUM-566",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "branch": "chatgpt/scrum-566-agent-runtime-corrective",
        "base_sha": "a" * 40,
        "head_sha": "b" * 40,
        "scope_hash": "sha256:" + "c" * 64,
        "profile_revision": "profile-r1",
        "graph_revision": "graph-r1",
        "node_registry_revision": "registry-r1",
        "policy_revision": "policy-r1",
        "source_kind": "canonical_agent_gate_state",
    }
    value.update(overrides)
    return value


def _binding(gate="G2_EXECUTION") -> dict:
    return {
        "node_id": "repo_delivery.scoped-file-write",
        "node_version": "1.0.0",
        "node_registry_revision": "registry-r1",
        "implementation_ref": "fixture:handler",
        "binding_digest": "sha256:" + "1" * 64,
        "gates": [gate],
        "entry_contract": ["gate_context"],
        "readback_contract": {"required": True},
        "side_effect_class": "read_only",
        "authority_requirements": {"gate_authority_required": True},
        "checkpoint_contract": {"required": True, "suspension": {"suspendable": True}},
        "next_route_contract": {
            "pass": {"disposition": "continue", "reason": "next", "next_node": None, "next_action": "next_action", "next_gate": None},
            "blocked": {"disposition": "stop", "reason": "blocked", "next_node": None, "next_action": None, "next_gate": gate},
            "pending": {"disposition": "wait", "reason": "wait", "next_node": "repo_delivery.scoped-file-write", "next_action": "wait", "next_gate": None},
            "retry": {"disposition": "retry", "reason": "retry", "next_node": "repo_delivery.scoped-file-write", "next_action": "retry", "next_gate": None},
        },
    }


def _semantic(binding, event):
    return {
        "outcome": "PASS", "reason_code": "LIVE_SEMANTIC_PASS",
        "requested_effects": [], "proposed_effects": [], "executed_effects": [],
        "next_contract": binding["next_route_contract"]["pass"],
        "implementation_invoked": True, "semantic_execution": True,
        "invocation_digest": "sha256:" + "2" * 64,
    }


def _route(node_id="repo_delivery.scoped-file-write"):
    return {
        "outcome": "ROUTE_SELECTED", "reason_code": "ROUTE_SELECTED",
        "current_node": node_id, "profile_revision": "profile-r1", "graph_revision": "graph-r1",
        "authority_granted": False, "write_authority_granted": False,
    }


def test_typed_live_event_contract_exists_for_every_g0_g6_boundary():
    bridge = _module("tools.node_architect.live_runtime_bridge")
    for gate in GATES:
        event = bridge.build_live_runtime_event(
            canonical_state=_state(), event_id=f"evt-{gate}", run_id=f"run-{gate}",
            gate=gate, requested_action="observe", scenario="standard_pr_delivery",
            input_payload={"gate_context": {"gate": gate}},
        )
        assert event["gate"] == gate
        assert event["live_agent_event"] is True
        assert event["synthetic"] is False
        assert event["source_kind"] == "canonical_agent_gate_state"
        for field in ("task_id", "run_id", "repository", "branch", "base_sha", "head_sha", "profile_revision", "graph_revision", "node_registry_revision", "policy_revision"):
            assert event[field]


def test_projection_only_event_is_rejected_as_runtime_evidence(tmp_path: Path):
    bridge = _module("tools.node_architect.live_runtime_bridge")
    event = bridge.build_live_runtime_event(
        canonical_state=_state(source_kind="jira_projection"), event_id="projection", run_id="run-proj",
        gate="G2_EXECUTION", requested_action="observe", scenario="projection",
        input_payload={"gate_context": {}},
    )
    out = bridge.dispatch_live_runtime_event(
        event=event, route_decision=_route(), implementation_registry={"bindings": [_binding()]},
        mode="shadow_readonly", semantic_handlers={"fixture:handler": _semantic}, capability_handlers={},
        readback_handler=lambda *args: {"status": "VERIFIED"}, evidence_root=tmp_path,
        state=bridge.LiveRuntimeState(),
    )
    assert out["status"] == "LIVE_RUNTIME_EVENT_REJECTED"
    assert out["reason_code"] == "PROJECTION_EVENT_NOT_CANONICAL_RUNTIME"


def test_required_not_applicable_and_blocked_are_policy_driven(tmp_path: Path):
    bridge = _module("tools.node_architect.live_runtime_bridge")
    base = bridge.build_live_runtime_event(
        canonical_state=_state(), event_id="applicability", run_id="run-app",
        gate="G4_MERGE", requested_action="merge_boundary", scenario="standard_pr_delivery",
        input_payload={"gate_context": {}},
    )
    for decision, expected in (("REQUIRED", "SEMANTIC_NODE_COMPLETE"), ("NOT_APPLICABLE", "LIVE_GATE_NOT_APPLICABLE"), ("BLOCKED", "LIVE_GATE_BLOCKED")):
        event = {**base, "event_id": f"app-{decision}", "idempotency_key": f"idem-{decision}"}
        out = bridge.dispatch_live_runtime_event(
            event=event,
            applicability_decision={"decision": decision, "policy_ref": "policy-r1", "decision_digest": "sha256:" + "3" * 64},
            route_decision=_route(), implementation_registry={"bindings": [_binding(gate="G4_MERGE")]},
            mode="shadow_readonly", semantic_handlers={"fixture:handler": _semantic}, capability_handlers={},
            readback_handler=lambda *args: {"status": "VERIFIED"}, evidence_root=tmp_path,
            state=bridge.LiveRuntimeState(),
        )
        assert out["status"] == expected


def test_duplicate_live_event_is_idempotent_but_conflicting_replay_fails(tmp_path: Path):
    bridge = _module("tools.node_architect.live_runtime_bridge")
    event = bridge.build_live_runtime_event(
        canonical_state=_state(), event_id="dupe", run_id="run-dupe", gate="G2_EXECUTION",
        requested_action="observe", scenario="standard_pr_delivery", input_payload={"gate_context": {}},
    )
    state = bridge.LiveRuntimeState()
    kwargs = dict(
        route_decision=_route(), implementation_registry={"bindings": [_binding()]}, mode="shadow_readonly",
        semantic_handlers={"fixture:handler": _semantic}, capability_handlers={},
        readback_handler=lambda *args: {"status": "VERIFIED"}, evidence_root=tmp_path, state=state,
    )
    first = bridge.dispatch_live_runtime_event(event=event, **kwargs)
    second = bridge.dispatch_live_runtime_event(event=event, **kwargs)
    assert first == second
    conflict = bridge.dispatch_live_runtime_event(event={**event, "requested_action": "changed"}, **kwargs)
    assert conflict["status"] == "LIVE_RUNTIME_EVENT_REJECTED"
    assert conflict["reason_code"] == "LIVE_RUNTIME_REPLAY_CONFLICT"


def test_ci_wait_checkpoint_resume_and_revision_drift(tmp_path: Path):
    bridge = _module("tools.node_architect.live_runtime_bridge")

    def pending(binding, event):
        return {
            "outcome": "PENDING", "reason_code": "CI_WAIT", "requested_effects": [],
            "next_contract": binding["next_route_contract"]["pending"],
            "implementation_invoked": True, "semantic_execution": True,
            "invocation_digest": "sha256:" + "4" * 64,
        }

    event = bridge.build_live_runtime_event(
        canonical_state=_state(), event_id="ci-wait", run_id="run-ci", gate="G2_EXECUTION",
        requested_action="ci_wait", scenario="ci_failure", input_payload={"gate_context": {}},
    )
    state = bridge.LiveRuntimeState()
    suspended = bridge.dispatch_live_runtime_event(
        event=event, route_decision=_route(), implementation_registry={"bindings": [_binding()]},
        mode="shadow_readonly", semantic_handlers={"fixture:handler": pending}, capability_handlers={},
        readback_handler=lambda *args: {"status": "VERIFIED"}, evidence_root=tmp_path, state=state,
    )
    assert suspended["status"] == "SEMANTIC_NODE_SUSPENDED"
    checkpoint = suspended["checkpoint"]

    resumed = bridge.resume_live_runtime_event(
        checkpoint=checkpoint,
        event={**event, "event_id": "ci-resume", "idempotency_key": "ci-resume-idem"},
        route_decision=_route(), implementation_registry={"bindings": [_binding()]}, mode="shadow_readonly",
        semantic_handlers={"fixture:handler": _semantic}, capability_handlers={},
        readback_handler=lambda *args: {"status": "VERIFIED"}, evidence_root=tmp_path, state=state,
    )
    assert resumed["status"] == "SEMANTIC_NODE_COMPLETE"

    stale = bridge.resume_live_runtime_event(
        checkpoint=checkpoint,
        event={**event, "event_id": "stale", "idempotency_key": "stale-idem", "head_sha": "d" * 40, "exact_revision": "d" * 40},
        route_decision=_route(), implementation_registry={"bindings": [_binding()]}, mode="shadow_readonly",
        semantic_handlers={"fixture:handler": _semantic}, capability_handlers={},
        readback_handler=lambda *args: {"status": "VERIFIED"}, evidence_root=tmp_path, state=state,
    )
    assert stale["status"] == "RESUME_BLOCKED"
    assert stale["reason_code"] == "CHECKPOINT_REVISION_DRIFT"


def test_route_decision_cannot_grant_node_authority(tmp_path: Path):
    bridge = _module("tools.node_architect.live_runtime_bridge")
    event = bridge.build_live_runtime_event(
        canonical_state=_state(), event_id="route-auth", run_id="run-auth", gate="G2_EXECUTION",
        requested_action="observe", scenario="standard_pr_delivery", input_payload={"gate_context": {}},
    )
    route = {**_route(), "authority_granted": True, "write_authority_granted": True}
    out = bridge.dispatch_live_runtime_event(
        event=event, route_decision=route, implementation_registry={"bindings": [_binding()]},
        mode="shadow_readonly", semantic_handlers={"fixture:handler": _semantic}, capability_handlers={},
        readback_handler=lambda *args: {"status": "VERIFIED"}, evidence_root=tmp_path, state=bridge.LiveRuntimeState(),
    )
    assert out["status"] == "LIVE_RUNTIME_EVENT_REJECTED"
    assert out["reason_code"] == "ROUTE_AUTHORITY_ESCALATION_REJECTED"
