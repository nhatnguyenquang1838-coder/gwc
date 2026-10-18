"""Synthetic unit fixtures, never receipts/qualification for the live Q0 run.

The old host fixture now verifies quarantine. These positive assertions retain
its node/provider/no-effect/continuation coverage at the profile's native actor
entrypoints. Executor-owned G0 fixtures below are synthetic actor-contract probes,
not the real Q0 boot: its source producer assigns G0/G1 to CONTROLLER. The CLI
must expose those Controller-local actions without loading a provider/Executor;
an Executor actor success alone still cannot complete G0 without gate evidence.
"""
from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path

import pytest

from tools.node_architect.q0_qualification import q0_qualification_profile
from tools.node_architect.universal_run_controller import UniversalControllerError
from tools.node_architect.universal_run_topology import create_node_allocation
from tools.node_architect.universal_runtime_profile import load_universal_v2_default_profile


def _sealed(body, field):
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return {**body, field: "sha256:" + hashlib.sha256(raw).hexdigest()}


def _native_g0_fixture():
    """Build isolated, explicitly synthetic native bindings; no live state read."""
    profile = load_universal_v2_default_profile()
    q0 = q0_qualification_profile()
    run_id = "test-only-q0-native-host-g0"
    node_id = "q0.qualification-campaign"
    allocation_id = f"{run_id}:{node_id}:r1"
    plan = _sealed({
        "schema_id": "gwc.universal-run.runtime-plan.v2", "schema_version": 2,
        "run_id": run_id, "revision": 1, "target_contract_ref": "unit-fixture-only",
        "node_allocations": [allocation_id], "runtime_epoch": profile["runtime_epoch"],
        "runtime_profile_ref": "core/node-architect/universal-runtime-default-profile.json",
        "runtime_default_profile_digest": profile["profile_digest"],
        "qualification_profile_ref": "core/node-architect/q0-live-qualification-profile.json",
        "qualification_profile_digest": q0["profile_digest"],
        "previous_digest": "sha256:" + "a" * 64,
        "source_binding": {"repository": "nhatnguyenquang1838-coder/gwc",
                           "branch": "fix/SCRUM-781-q0-unit-fixture",
                           "pre_head_sha": "b" * 40},
    }, "digest")
    allocation = create_node_allocation(
        record_id=f"NA-{run_id}-r1", run_id=run_id,
        node_allocation_id=allocation_id, kind="WORK", requirement="REQUIRED",
        created_at="2026-10-03T00:00:00Z", created_by={"profile": "test-only"},
        source_refs=[node_id], predecessor_refs=[plan["previous_digest"]],
    )
    state = _sealed({
        "schema_id": "gwc.universal-run.run-state.v2", "schema_version": 2,
        "run_id": run_id, "sequence": 1, "predecessor_sequence": 0,
        "active_gate": "UR.G0", "runtime_epoch": profile["runtime_epoch"],
        "execution_refs": {
            "branch": plan["source_binding"]["branch"],
            "node_allocation_id": allocation_id,
            "node_allocation_ref": "unit-fixture.json#record_id=" + allocation["record_id"],
            "base_sha": "c" * 40, "candidate_sha": plan["source_binding"]["pre_head_sha"],
            "qualification_profile_digest": q0["profile_digest"],
            "runtime_plan_digest": plan["digest"], "cursor_ref": f"{run_id}:UR.G0:seq1",
        },
        "gate_evidence": {}, "typed_next": "EXECUTE_UNIVERSAL_ACTION",
        "next_owner": "EXECUTOR", "evidence_gap": ["UNDERSTANDING_RECEIPT"],
        "consumed_receipts": [],
    }, "state_digest")
    return profile, {"runtime_plan": plan, "run_state": state, "node_allocation": allocation}


def _profile_actor(profile, key):
    module_name, name = profile[key].split(":", 1)
    return getattr(importlib.import_module(module_name), name)


class ReadOnlyQ0Provider:
    name = "q0-native-readonly-unit-fixture"

    def __init__(self):
        self.packs = []

    def run(self, pack):
        self.packs.append(pack)
        return {"outcome": "PASS", "reason_code": "TEST_ONLY_Q0_READ_ONLY_PROBE",
                "tool_requests": []}


def _execute_g0(tmp_path):
    profile, manifest = _native_g0_fixture()
    controller = _profile_actor(profile, "controller_entrypoint").from_manifest(
        profile=profile, manifest=manifest,
    )
    assignment = controller.assign_current_action()
    provider = ReadOnlyQ0Provider()
    event = {"event_id": "test-only-q0-g0-event", "effect_class": "read_only"}
    receipt = _profile_actor(profile, "executor_entrypoint")().execute(
        assignment=assignment, provider=provider, event=event,
        evidence_root=tmp_path / "unit-receipts", max_iterations=1,
    )
    return controller, assignment, provider, event, receipt


def test_q0_native_actors_run_ur_g0_with_provider_readback_and_controller_continuation(tmp_path):
    controller, assignment, provider, event, receipt = _execute_g0(tmp_path)
    # Synthetic evidence exercises the existing G0 contract, not live approval.
    evidence = {"UNDERSTANDING_RECEIPT": {"fixture_only": True, "goal": "unit probe"}}
    decision = controller.consume_executor_receipt(receipt, evidence_artifacts=evidence)

    assert receipt["schema_id"] == "gwc.universal-run.executor-action-receipt.v2"
    assert receipt["host_status"] == "ACTION_COMPLETE"
    assert receipt["route_id"] == "UNIVERSAL_RUN_NEW_RUNTIME"
    assert receipt["node_id"] == "q0.qualification-campaign"
    assert receipt["gate"] == "UR.G0" and receipt["action"] == "q0_understand"
    assert receipt["authority_granted"] is False and receipt["executed_effects"] == []
    assert receipt["actor"] == "EXECUTOR"
    assert len(provider.packs) == 1
    assert provider.packs[0] == {**assignment, "event": event, "max_iterations": 1}
    disk = tmp_path / "unit-receipts" / receipt["evidence_refs"]["executor_receipt"]
    assert json.loads(disk.read_text()) == receipt
    assert decision["next_gate"] == "UR.G1"
    assert decision["typed_next"] == "CONTINUE_UNIVERSAL_LANE_REMEDIATION"
    assert decision["authority_granted"] is False and decision["executed_effects"] == []


def test_q0_native_g0_actor_success_without_understanding_does_not_advance(tmp_path):
    controller, _, provider, _, receipt = _execute_g0(tmp_path)
    before = json.loads(json.dumps(controller.run_state))
    with pytest.raises(UniversalControllerError, match="Q0_GATE_EVIDENCE_REQUIRED"):
        controller.consume_executor_receipt(receipt)
    assert controller.run_state == before
    assert len(provider.packs) == 1


@pytest.mark.parametrize("with_factory", [False, True])
@pytest.mark.parametrize("gate,typed_next,action", [
    ("UR.G0", "Q0_UNDERSTAND", "q0_understand"),
    ("UR.G1", "Q0_PLAN_DECOMPOSE", "q0_plan_decompose"),
])
def test_native_cli_controller_owned_assignment_never_loads_provider_or_dispatches_executor(
    tmp_path, monkeypatch, capsys, with_factory, gate, typed_next, action,
):
    from tools.node_architect import agent_runtime_cli
    from tools.node_architect.universal_run_execution import UniversalExecutor

    _, native_manifest = _native_g0_fixture()
    body = {k: v for k, v in native_manifest["run_state"].items() if k != "state_digest"}
    body.update(active_gate=gate, next_owner="CONTROLLER", typed_next=typed_next)
    body["execution_refs"] = {**body["execution_refs"], "cursor_ref": f"{body['run_id']}:{gate}:seq1"}
    body["evidence_gap"] = ["UNDERSTANDING_RECEIPT" if gate == "UR.G0" else "PLAN_RECEIPT"]
    native_manifest["run_state"] = _sealed(body, "state_digest")
    evidence_root = tmp_path / "must-not-exist"
    manifest = tmp_path / "controller-owned.json"
    manifest.write_text(json.dumps({
        "provider_name": "unit-provider", "event": {"event_id": "unit-controller-local"},
        "universal_run": {**native_manifest, "evidence_root": str(evidence_root)},
    }))
    original = manifest.read_bytes()
    calls = []

    def forbidden_factory(*args, **kwargs):
        calls.append("provider_factory")
        raise AssertionError("Controller-local action must not load a provider")

    def forbidden_execute(*args, **kwargs):
        calls.append("executor")
        raise AssertionError("Controller-local action must not enter Executor")

    monkeypatch.setattr(agent_runtime_cli, "_load_factory", forbidden_factory)
    monkeypatch.setattr(UniversalExecutor, "execute", forbidden_execute)
    argv = ["--manifest", str(manifest)]
    if with_factory:
        argv += ["--provider-factory", "unit:must_not_load"]
    code = agent_runtime_cli.main(argv)
    result = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert code == 1
    assert result["status"] == "BLOCKED"
    assert result["reason_code"] == "CONTROLLER_LOCAL_ACTION_REQUIRED", result
    local = result["controller_action"]
    assert local["schema_id"] == "gwc.universal-run.controller-local-action.v2"
    assert local["actor"] == local["next_owner"] == "CONTROLLER"
    assert local["gate"] == gate and local["action"] == action
    assert local["typed_next"] == typed_next
    assert local["effect_authority"] == "NONE"
    assert local["authority_granted"] is False and local["executed_effects"] == []
    assert result["authority_granted"] is False and result["executed_effects"] == []
    assert result["legacy_fallback"] is False
    assert "executor_receipt" not in result and "controller_decision" not in result
    assert calls == []
    assert manifest.read_bytes() == original
    assert not evidence_root.exists()


def test_q0_native_cli_g0_does_not_confuse_actor_success_with_gate_completion(tmp_path, monkeypatch, capsys):
    from tools.node_architect import agent_runtime_cli

    _, native_manifest = _native_g0_fixture()
    provider = ReadOnlyQ0Provider()
    evidence_root = tmp_path / "cli-unit-receipts"
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "provider_name": provider.name, "event": {"event_id": "test-only-cli-g0"},
        "universal_run": {**native_manifest, "evidence_root": str(evidence_root)},
    }))
    monkeypatch.setattr(agent_runtime_cli, "_load_factory", lambda _: lambda: provider)
    code = agent_runtime_cli.main(["--manifest", str(manifest), "--provider-factory", "unit:factory"])
    result = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert code == 1
    assert result["status"] == "BLOCKED" and result["reason_code"] == "GWC_RUNTIME_DEFECT"
    assert "UniversalControllerError" in result["message"]
    assert result["legacy_fallback"] is False
    assert result["authority_granted"] is False and result["executed_effects"] == []
    assert len(provider.packs) == 1
    receipts = list(evidence_root.rglob("executor-action-receipt.json"))
    assert len(receipts) == 1
    assert json.loads(receipts[0].read_text())["host_status"] == "ACTION_COMPLETE"
