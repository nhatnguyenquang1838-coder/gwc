from __future__ import annotations

import unittest
import contextlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.node_architect import agent_runtime_cli
from tools.node_architect.universal_run_node import RecursiveRunDag
from tools.node_architect.universal_run_topology import create_node_allocation, create_run_manifest_revision

TS = "2026-10-23T00:00:00Z"
ACTOR = {"kind": "agent", "id": "recursive-adapter-test"}


def _root():
    return create_run_manifest_revision(
        record_id="root-record", run_id="recursive-root-adapter", revision=1,
        run_kind="ROOT", created_at=TS, created_by=ACTOR,
    )


def _allocation():
    return create_node_allocation(
        record_id="child-allocation", run_id="recursive-root-adapter",
        node_allocation_id="child-work", kind="WORK", requirement="REQUIRED",
        created_at=TS, created_by=ACTOR,
    )


def _target_contract(run_id, target_id, children, allocations, parent_digest=None,
                    lineage=None):
    contract = {"schema_version": "1.0", "run_id": run_id, "target_id": target_id,
                "required_children": list(children), "required_child_allocations": list(allocations)}
    if parent_digest is not None:
        contract.update(lineage or {})
        contract["parent_contract_digest"] = parent_digest
    digest_body = json.dumps(contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    import hashlib
    contract["contract_digest"] = "sha256:" + hashlib.sha256(digest_body).hexdigest()
    return contract


def _semantic_complete(run_id, gate):
    return {
        "status": "SEMANTIC_NODE_COMPLETE",
        "reason_code": "SEMANTIC_NODE_COMPLETE",
        "run_id": run_id,
        "gate": gate,
        "readback": {"status": "VERIFIED", "digest": f"readback:{run_id}:{gate}"},
        "canonical_readback_verified": True,
        "evidence_summary": {"artifact_type": "semantic-evidence-summary", "ref": f"evidence:{run_id}:{gate}"},
        "next_route": {"disposition": "stop", "next_gate": gate, "next_node": None, "next_action": None,
                       "automatic_gate_advance": False},
        "authority_granted": False,
        "executed_effects": [],
    }


def _case_semantic_host_responses_produce_gate_evidence_then_wait_for_real_g6_acceptance():
    calls = []

    def host(**kwargs):
        calls.append(kwargs)
        return _semantic_complete(kwargs["run_id"], kwargs["gate"])

    allocation = _allocation()
    result = RecursiveRunDag(runtime_event=host).execute(
        root_manifest=_root(),
        child_node_allocations=[{"child_run_id": "recursive-child-adapter", "node_allocation": allocation}],
        authority=None,
        canonical_state={"task_id": "SCRUM-TEST"},
        route_context={"context": {"target_contract": _target_contract(
            "recursive-root-adapter", "test-target", ["recursive-child-adapter"], [allocation["node_allocation_id"]])}},
    )

    assert [call["gate"] for call in calls if call["run_id"] == "recursive-child-adapter"] == [
        "G0", "G1", "G2", "G3", "G4", "G5", "G6",
    ]
    child = result["children"][0]
    assert child["status"] == "WAITING"
    assert child["failure_code"] == "G6_ACCEPTANCE_EVIDENCE_MISSING"
    assert child["gate_evidence"]["G5"]["semantic_status"] == "SEMANTIC_NODE_COMPLETE"
    assert child["gate_readbacks"]["G5"]["status"] == "VERIFIED"
    assert child["g6_receipt"] is None
    assert "G6" not in child["gate_evidence"]
    assert result["status"] == "WAITING"
    assert result["children"][0]["c1_status"] == "INTEGRATION_PENDING"


def _case_provider_cannot_select_next_gate_or_route_in_recursive_host_result():
    def host(**kwargs):
        response = _semantic_complete(kwargs["run_id"], kwargs["gate"])
        response["next_route"] = {"disposition": "continue", "next_gate": "G6_PRODUCTION_DATA",
                                   "next_node": "attacker.node", "next_action": "attacker"}
        return response

    result = RecursiveRunDag(runtime_event=host).execute(
        root_manifest=_root(), child_node_allocations=[], authority=None,
        canonical_state={"task_id": "SCRUM-TEST"},
        route_context={"context": {"target_contract": _target_contract(
            "recursive-root-adapter", "test-target", [], [])}},
    )

    assert result["status"] == "WAITING"
    assert result["failure_code"] == "CANONICAL_NEXT_ROUTE_INVALID"
    assert result["gate_evidence"] == {}
    assert result["g6_receipt"] is None


def _case_semantic_blocked_maps_to_waiting_without_gate_evidence():
    def host(**kwargs):
        return {"status": "SEMANTIC_NODE_BLOCKED", "reason_code": "HOST_READBACK_REJECTED"}

    result = RecursiveRunDag(runtime_event=host).execute(
        root_manifest=_root(), child_node_allocations=[], authority=None,
        canonical_state={"task_id": "SCRUM-TEST"},
        route_context={"context": {"target_contract": _target_contract(
            "recursive-root-adapter", "test-target", [], [])}},
    )
    assert result["status"] == "WAITING"
    assert result["failure_code"] == "HOST_READBACK_REJECTED"
    assert result["gate_evidence"] == {}
    assert result["g6_receipt"] is None


def _case_cli_recursive_mode_dispatches_slot83_and_holds_c2_g2():
    repository_root = Path(__file__).resolve().parents[1]
    with TemporaryDirectory() as temp:
        tmp = Path(temp)
        marker = tmp / "factory-called"
        factory = tmp / "configured_provider.py"
        factory.write_text(
            "from pathlib import Path\n"
            "class Provider:\n"
            "    name = 'recursive-configured-provider'\n"
            "    def run(self, pack):\n"
            "        return {'outcome': 'PASS', 'tool_requests': []}\n"
            "def build_provider():\n"
            f"    Path({str(marker)!r}).write_text('created')\n"
            "    return Provider()\n",
            encoding="utf-8",
        )
        run_id = "cli-recursive-root"
        from tools.node_architect.universal_run_topology import create_run_manifest_revision
        root_manifest = create_run_manifest_revision(
            record_id="cli-root-record", run_id=run_id, revision=1, run_kind="ROOT",
            created_at=TS, created_by=ACTOR,
        )
        read = lambda name: json.loads((repository_root / "core/node-architect" / name).read_text(encoding="utf-8"))
        gate_names = ("UR.G0", "UR.G1", "UR.G2", "UR.G3", "UR.G4", "UR.G5", "UR.G6")
        payload = {
            "mode": "recursive_run",
            "provider_name": "recursive-configured-provider",
            "recursive_run": {
                "root_manifest": root_manifest,
                "child_node_allocations": [],
                "gate_actions": dict(zip(gate_names, ("UNDERSTAND", "PLAN", "EXECUTE", "VERIFY", "INTEGRATE", "VALIDATE-IN-TARGET", "ACCEPT/HANDOFF"))),
            },
            "event": {
                "canonical_state": {
                    "task_id": "SCRUM-TEST", "repository": "example/gwc", "branch": "test-branch",
                    "base_sha": "a" * 40, "head_sha": "b" * 40, "scope_hash": "sha256:" + "c" * 64,
                    "profile_revision": read("gate-node-route-profile.json")["revision"],
                    "graph_revision": "scrum-104-20260726",
                    "node_registry_revision": "scrum-288-entry-schema-validation-20260809-r1",
                    "policy_revision": "policy-r1", "source_kind": "canonical_agent_gate_state",
                },
                "run_id": run_id, "event_id": "cli-recursive-event", "gate": "G0_CONTEXT",
                "requested_action": "RUN", "scenario": "ci_failure", "workflow_mode": "normal",
                "input_payload": {}, "instruction_refs": [], "role_overlay_refs": [], "required_skill_names": [],
                "mode": "shadow_readonly", "authority": None, "capability_handlers": {},
                "readback_handler": None, "evidence_root": str(tmp / "evidence"), "state": None,
                "root": str(repository_root), "route_profile": read("gate-node-route-profile.json"),
                "node_registry": read("node-registry.json"), "graph_registry": read("runtime-graph-registry.json"),
                "route_context": {"context": {"universal_run_manifest": root_manifest,
                               "target_contract": _target_contract(run_id, "test-target", [], [])}},
            },
        }
        manifest = tmp / "manifest.json"
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = agent_runtime_cli.main([
                "--manifest", str(manifest), "--provider-factory", f"{factory}:build_provider",
                "--output", str(tmp / "result.json"),
            ])
        result = json.loads((tmp / "result.json").read_text(encoding="utf-8"))
        assert marker.read_text(encoding="utf-8") == "created"
        assert code == 1
        assert result["status"] == "WAITING"
        assert result["failure_code"] == "AUTHORITY_TRUST_ANCHOR_UNAVAILABLE"
        assert result["c1_status"] == "INTEGRATION_PENDING"
        assert result["g6_receipt"] is None
        assert set(result["gate_evidence"]) == {"G0", "G1"}
        for gate in ("G0", "G1"):
            assert result["gate_evidence"][gate]["semantic_status"] == "SEMANTIC_NODE_COMPLETE"
            result_path = Path(result["gate_evidence"][gate]["evidence_summary"]["paths"][2])
            node_result = json.loads(result_path.read_text(encoding="utf-8"))
            assert node_result["payload"]["semantic_result"]["provider_result"]["status"] == "ROUTE_SELECTED"
        assert "G2" not in result["gate_evidence"]


class RecursiveSemanticAdapterTests(unittest.TestCase):
    def test_core_universal_instruction_validates_and_builds_pack_from_exact_route(self):
        from tools.node_architect.agent_instruction_bundle import resolve_agent_instruction_bundle
        from tools.node_architect.build_node_instruction_pack import build_node_instruction_pack
        from tools.node_architect.validate_node_instruction import validate_universal_instruction
        root = Path(__file__).resolve().parents[1]
        profile = json.loads((root / "core/node-architect/gate-node-route-profile.json").read_text())
        route = next(item for item in profile["routes"] if item["gate"] == "UR.G4")
        card = json.loads((root / route["node_instruction_ref"]).read_text())
        descriptor = json.loads((root / route["node_descriptor_ref"]).read_text())
        node = json.loads((root / "core/node-architect/runtime-node-extension-registry.json").read_text())["extensions"][1]["node"]
        report = validate_universal_instruction(card=card, descriptor=descriptor, registry_node=node,
                                                route=route, active_gate="UR.G4", action="INTEGRATE", mode="normal")
        self.assertTrue(report.valid, report.reason_codes)
        bundle = resolve_agent_instruction_bundle(
            root=root, instruction_refs=(), role_overlay_refs=(), required_skill_names=(),
            node_instruction_ref=route["node_instruction_ref"],
        )
        pack = build_node_instruction_pack(
            {"run_id": "run-1", "task_id": "task-1", "repository": "org/repo",
             "preprod_base_sha": "a" * 40, "working_branch": "feature/test",
             "scope_hash": "sha256:" + "b" * 64, "graph_revision": "graph-r1",
             "policy_revision": "policy-r1", "idempotency_key": "run-1:UR.G4",
             "allowed_paths": [], "prohibited_paths": [], "authorized_actions": [],
             "validation_commands": []},
            gate="UR.G4", requested_action="INTEGRATE", node_id=node["id"],
            node_version=node["version"], implementation_ref=route["implementation"]["ref"],
            instruction_bundle=bundle,
        )
        self.assertEqual(pack.node_instruction_ref, route["node_instruction_ref"])
        self.assertTrue(pack.content_digest.startswith("sha256:"))

    def test_route_context_keeps_task_and_run_identity_separate(self):
        from tools.node_architect.agent_runtime_entrypoint import _route_context
        context = _route_context(
            canonical_state={"task_id": "TASK-1"}, run_id="child-run-1", gate="UR.G4",
            requested_action="INTEGRATE", workflow_mode="normal", input_payload={}, supplied=None,
        )
        self.assertEqual(context["task_id"], "TASK-1")
        self.assertEqual(context["run_id"], "child-run-1")

    def test_live_bridge_accepts_universal_gates_without_legacy_aliasing(self):
        from tools.node_architect.live_runtime_bridge import build_live_runtime_event
        event = build_live_runtime_event(
            canonical_state={"task_id": "TASK-1", "source_kind": "canonical_agent_gate_state"},
            event_id="evt-1", run_id="child-run-1", gate="UR.G4", requested_action="INTEGRATE",
            scenario="generic", input_payload={},
        )
        self.assertEqual(event["gate"], "UR.G4")
        self.assertEqual(event["run_id"], "child-run-1")

    def test_cli_recursive_mode_dispatches_slot83_and_holds_c2_g2(self):
        _case_cli_recursive_mode_dispatches_slot83_and_holds_c2_g2()

    def test_semantic_host_responses_produce_gate_evidence_then_wait_for_real_g6_acceptance(self):
        _case_semantic_host_responses_produce_gate_evidence_then_wait_for_real_g6_acceptance()

    def test_semantic_blocked_maps_to_waiting_without_gate_evidence(self):
        _case_semantic_blocked_maps_to_waiting_without_gate_evidence()

    def test_provider_cannot_select_next_gate_or_route_in_recursive_host_result(self):
        _case_provider_cannot_select_next_gate_or_route_in_recursive_host_result()
