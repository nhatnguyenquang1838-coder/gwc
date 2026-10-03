from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools.node_architect.q0_qualification import q0_qualification_profile
from tools.node_architect.resolve_gate_node_route import resolve_gate_node_route
from tools.node_architect.universal_run_continuation import create_or_recover_runtime_plan
from tools.node_architect.universal_run_execution import execute_universal_run_node
from tools.node_architect.universal_run_topology import create_node_allocation

ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "scrum781-q0-adapter-test"
NODE_ID = "q0.qualification-campaign"


class ReadOnlyProvider:
    name = "universal-run-adapter-test"

    def run(self, pack):
        return {
            "outcome": "PASS",
            "reason_code": "READ_ONLY_ADAPTER_TEST",
            "tool_requests": [],
            "next_contract_key": "pass",
        }


def _bindings():
    profile = json.loads((ROOT / "core/node-architect/gate-node-route-profile.json").read_text())
    nodes = json.loads((ROOT / "core/node-architect/node-registry.json").read_text())
    graph = json.loads((ROOT / "core/node-architect/runtime-graph-registry.json").read_text())
    return profile, nodes, graph


def _allocation():
    return create_node_allocation(
        record_id="NA-Q0-ADAPTER-TEST",
        run_id=RUN_ID,
        node_allocation_id=f"{RUN_ID}:{NODE_ID}",
        kind="WORK",
        requirement="REQUIRED",
        created_at="2026-10-02T18:00:00Z",
        created_by={"profile": "dwa-hermes"},
        source_refs=[NODE_ID],
    )


def _event_kwargs(tmp_path: Path):
    profile, nodes, graph = _bindings()
    q0 = q0_qualification_profile()
    return {
        "canonical_state": {
            "task_id": "SCRUM-781",
            "repository": "nhatnguyenquang1838-coder/gwc",
            "branch": "fix/SCRUM-781-q0-canonical",
            "base_sha": "9c2c1b1ec50a2dd94f531db580da9db1521ce260",
            "head_sha": "b5f68f210faa3915098793c56b8d16135a0cffee",
            "scope_hash": "sha256:" + "c" * 64,
            "profile_revision": profile["revision"],
            "graph_revision": profile["bound_graph_revision"],
            "node_registry_revision": nodes["revision"],
            "policy_revision": "q0-profile-test",
            "runtime_epoch": "UNIVERSAL_V2_DEVELOPMENT",
            "source_kind": "canonical_agent_gate_state",
        },
        "event_id": "q0-adapter-event",
        "occurred_at": "2026-10-02T18:00:00Z",
        "scenario": "q0_universal_execution_adapter_test",
        "input_payload": {"q0_profile": q0, "effect_class": "read_only"},
        "instruction_refs": ("AGENTS.md",),
        "role_overlay_refs": (),
        "required_skill_names": (),
        "provider": ReadOnlyProvider(),
        "provider_registry": None,
        "mode": "shadow_readonly",
        "authority": None,
        "capability_handlers": {},
        "readback_handler": lambda *args: {"status": "VERIFIED"},
        "evidence_root": tmp_path / "host-evidence",
        "state": None,
        "root": ROOT,
        "route_profile": profile,
        "node_registry": nodes,
        "graph_registry": graph,
        "implementation_registry": None,
        "route_resolver": resolve_gate_node_route,
    }


def test_universal_run_adapter_executes_node_records_evidence_and_advances_typed_next(tmp_path: Path):
    allocation = _allocation()
    plan = create_or_recover_runtime_plan(
        run_id=RUN_ID,
        revision=1,
        target_contract_ref="q0-live-qualification-profile",
        node_allocations=[allocation["node_allocation_id"]],
    )
    run_state = {
        "schema_id": "gwc.universal-run.run-state",
        "run_id": RUN_ID,
        "sequence": 3,
        "active_gate": "UR.G2",
        "runtime_epoch": "UNIVERSAL_V2_DEVELOPMENT",
        "execution_refs": {
            "runtime_plan_ref": "q0-runtime-plan-r1",
            "runtime_plan_digest": plan["digest"],
            "cursor_ref": "q0-run-state-seq3",
        },
        "future_contract_refs": {},
        "gate_evidence": {},
    }

    result = execute_universal_run_node(
        route_id="UNIVERSAL_RUN_NEW_RUNTIME",
        runtime_plan=plan,
        run_state=run_state,
        node_allocation=allocation,
        event_kwargs=_event_kwargs(tmp_path),
        evidence_root=tmp_path / "ledger",
        parent_composition={
            "parent_run_id": "SCRUM-780",
            "acceptance_contract_ref": "SCRUM-780-Q0-composition-test",
            "required_child_run_ids": ["SCRUM-781"],
            "child_results": [
                {"child_run_id": "SCRUM-781", "terminal_state": "ACCEPTED", "output_digest": "sha256:" + "d" * 64}
            ],
        },
    )

    assert result["host_result"]["status"] == "SEMANTIC_NODE_COMPLETE", result["host_result"]
    assert result["host_result"]["authority_granted"] is False
    assert result["host_result"]["executed_effects"] == []
    assert result["node_id"] == NODE_ID
    assert result["node_next_route"]["next_action"] == "q0_continue_universal_lifecycle"
    assert result["controller_continuation"]["typed_next"] == "CONTINUE_UNIVERSAL_LANE_REMEDIATION"
    assert result["controller_continuation"]["successor_run_state"]["active_gate"] == "UR.G3"
    assert result["execution_receipt"]["artifact_type"] == "universal-run-execution-receipt"
    assert result["evidence_ledger"]["records"]["next-route-decision"]["payload"]["typed_next"]
    assert result["parent_composition"]["ok"] is True


def test_universal_run_adapter_keeps_gate_cursor_when_g0_receipt_is_missing(tmp_path: Path):
    allocation = _allocation()
    plan = create_or_recover_runtime_plan(
        run_id=RUN_ID,
        revision=1,
        target_contract_ref="q0-live-qualification-profile",
        node_allocations=[allocation["node_allocation_id"]],
    )
    run_state = {
        "schema_id": "gwc.universal-run.run-state",
        "run_id": RUN_ID,
        "sequence": 1,
        "active_gate": "UR.G0",
        "runtime_epoch": "UNIVERSAL_V2_DEVELOPMENT",
        "execution_refs": {
            "runtime_plan_ref": "q0-runtime-plan-r1",
            "runtime_plan_digest": plan["digest"],
            "cursor_ref": "q0-run-state-seq1",
        },
        "future_contract_refs": {},
        "gate_evidence": {},
    }
    result = execute_universal_run_node(
        route_id="UNIVERSAL_RUN_NEW_RUNTIME",
        runtime_plan=plan,
        run_state=run_state,
        node_allocation=allocation,
        event_kwargs=_event_kwargs(tmp_path),
        evidence_root=tmp_path / "ledger",
    )
    continuation = result["controller_continuation"]
    assert result["host_result"]["status"] == "SEMANTIC_NODE_COMPLETE"
    assert continuation["typed_next"] == "AWAIT_GATE_EVIDENCE"
    assert continuation["gate_advanced"] is False
    assert continuation["successor_run_state"]["sequence"] == 1
    assert continuation["successor_run_state"]["active_gate"] == "UR.G0"


def test_universal_run_adapter_rejects_malformed_gate_evidence_before_host_dispatch(tmp_path: Path):
    allocation = _allocation()
    plan = create_or_recover_runtime_plan(
        run_id=RUN_ID,
        revision=1,
        target_contract_ref="q0-live-qualification-profile",
        node_allocations=[allocation["node_allocation_id"]],
    )
    run_state = {
        "schema_id": "gwc.universal-run.run-state",
        "run_id": RUN_ID,
        "sequence": 3,
        "active_gate": "UR.G2",
        "runtime_epoch": "UNIVERSAL_V2_DEVELOPMENT",
        "execution_refs": {
            "runtime_plan_ref": "q0-runtime-plan-r1",
            "runtime_plan_digest": plan["digest"],
            "cursor_ref": "q0-run-state-seq3",
        },
        "future_contract_refs": {},
        "gate_evidence": "tampered-not-a-map",
    }
    from tools.node_architect.universal_run_execution import UniversalRunExecutionError
    with pytest.raises(UniversalRunExecutionError, match="RUN_STATE_GATE_EVIDENCE_INVALID"):
        execute_universal_run_node(
            route_id="UNIVERSAL_RUN_NEW_RUNTIME",
            runtime_plan=plan,
            run_state=run_state,
            node_allocation=allocation,
            event_kwargs=_event_kwargs(tmp_path),
            evidence_root=tmp_path / "ledger",
        )


def test_universal_run_adapter_rejects_plan_allocation_binding_drift(tmp_path: Path):
    allocation = _allocation()
    plan = create_or_recover_runtime_plan(
        run_id=RUN_ID,
        revision=1,
        target_contract_ref="q0-live-qualification-profile",
        node_allocations=["another-run:other-node"],
    )
    with pytest.raises(ValueError, match="NODE_ALLOCATION_NOT_BOUND_TO_PLAN"):
        execute_universal_run_node(
            route_id="UNIVERSAL_RUN_NEW_RUNTIME",
            runtime_plan=plan,
            run_state={
                "schema_id": "gwc.universal-run.run-state",
                "run_id": RUN_ID,
                "sequence": 3,
                "active_gate": "UR.G2",
                "runtime_epoch": "UNIVERSAL_V2_DEVELOPMENT",
                "execution_refs": {
                    "runtime_plan_ref": "q0-runtime-plan-r1",
                    "runtime_plan_digest": plan["digest"],
                    "cursor_ref": "q0-run-state-seq3",
                },
                "future_contract_refs": {},
                "gate_evidence": {},
            },
            node_allocation=allocation,
            event_kwargs=_event_kwargs(tmp_path),
            evidence_root=tmp_path / "ledger",
        )


def test_agent_runtime_cli_executes_bound_universal_run_through_real_adapter(tmp_path: Path, capsys):
    from tools.node_architect import agent_runtime_cli

    provider_module = tmp_path / "q0_configured_provider.py"
    provider_module.write_text(
        "class Provider:\n"
        "    name = 'q0-configured-test-provider'\n"
        "    def run(self, pack):\n"
        "        return {'terminal_outcome':'SUCCESS','changed_paths':[],'recorded_actions':[],'validation_passed':True,'next_action':'stop'}\n"
        "def build_provider(): return Provider()\n",
        encoding="utf-8",
    )
    allocation = _allocation()
    plan = create_or_recover_runtime_plan(
        run_id=RUN_ID,
        revision=1,
        target_contract_ref="q0-live-qualification-profile",
        node_allocations=[allocation["node_allocation_id"]],
    )
    run_state = {
        "schema_id": "gwc.universal-run.run-state",
        "run_id": RUN_ID,
        "sequence": 3,
        "active_gate": "UR.G2",
        "runtime_epoch": "UNIVERSAL_V2_DEVELOPMENT",
        "execution_refs": {
            "runtime_plan_ref": "q0-runtime-plan-r1",
            "runtime_plan_digest": plan["digest"],
            "cursor_ref": "q0-run-state-seq3",
        },
        "future_contract_refs": {},
        "gate_evidence": {},
    }
    event = _event_kwargs(tmp_path)
    for key in ("provider", "provider_registry", "readback_handler", "route_resolver"):
        event.pop(key, None)
    event["root"] = str(ROOT)
    event["evidence_root"] = str(tmp_path / "host-evidence")
    from tools.node_architect.canonical_readback import digest_evidence
    readback_evidence = {
        "runtime_plan_digest": plan["digest"],
        "node_allocation_id": allocation["node_allocation_id"],
        "source_sha256": hashlib.sha256((ROOT / "tools/node_architect/universal_run_execution.py").read_bytes()).hexdigest(),
    }
    (tmp_path / "canonical-readback.json").write_text(json.dumps(readback_evidence), encoding="utf-8")
    event["input_payload"]["canonical_readback"] = {
        "status": "VERIFIED",
        "source_kind": "filesystem_readback",
        "run_id": RUN_ID,
        "event_id": event["event_id"] + "-1",
        "node_id": NODE_ID,
        "task_id": "SCRUM-781",
        "repository": event["canonical_state"]["repository"],
        "branch": event["canonical_state"]["branch"],
        "base_sha": event["canonical_state"]["base_sha"],
        "head_sha": event["canonical_state"]["head_sha"],
        "scope_hash": event["canonical_state"]["scope_hash"],
        "evidence_refs": [str(tmp_path / "canonical-readback.json")],
        "evidence": readback_evidence,
        "evidence_digest": digest_evidence(readback_evidence),
    }
    manifest = {
        "provider_name": "q0-configured-test-provider",
        "event": event,
        "universal_run": {
            "route_id": "UNIVERSAL_RUN_NEW_RUNTIME",
            "runtime_plan": plan,
            "run_state": run_state,
            "node_allocation": allocation,
            "evidence_root": str(tmp_path / "ledger"),
            "parent_composition": None,
        },
    }
    manifest_path = tmp_path / "q0-universal-run-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    exit_code = agent_runtime_cli.main([
        "--manifest", str(manifest_path),
        "--provider-factory", f"{provider_module}:build_provider",
        "--max-iterations", "3",
    ])
    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0, (output.get("host_result") or {}).get("reason_code")
    assert output["status"] == "UNIVERSAL_RUN_NODE_COMPLETE"
    assert output["host_result"]["status"] == "SEMANTIC_NODE_COMPLETE"
    assert output["controller_continuation"]["successor_run_state"]["active_gate"] == "UR.G3"
    assert output["authority_granted"] is False
    assert output["executed_effects"] == []
    assert Path(output["evidence_ledger"]["summary"]["events_path"]).is_file()
