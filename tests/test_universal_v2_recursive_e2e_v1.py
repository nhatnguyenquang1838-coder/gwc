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

    result = RecursiveRunDag(runtime_event=host).execute(
        root_manifest=_root(),
        child_node_allocations=[{"child_run_id": "recursive-child-adapter", "node_allocation": _allocation()}],
        authority=None,
        canonical_state={"task_id": "SCRUM-TEST"},
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
    )
    assert result["status"] == "WAITING"
    assert result["failure_code"] == "HOST_READBACK_REJECTED"
    assert result["gate_evidence"] == {}
    assert result["g6_receipt"] is None


def _case_cli_recursive_mode_calls_canonical_host_and_fails_closed_on_missing_route():
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
        gate_names = ("G0_CONTEXT", "G1_ALIGNMENT", "G2_EXECUTION", "G3_PR", "G4_INTEGRATE", "G5_VALIDATE_TARGET", "G6_ACCEPT_HANDOFF")
        payload = {
            "mode": "recursive_run",
            "provider_name": "recursive-configured-provider",
            "recursive_run": {
                "root_manifest": root_manifest,
                "child_node_allocations": [],
                "gate_actions": {gate: "resolve_execution_node" for gate in gate_names},
            },
            "event": {
                "canonical_state": {
                    "task_id": "SCRUM-TEST", "repository": "example/gwc", "branch": "test-branch",
                    "base_sha": "a" * 40, "head_sha": "b" * 40, "scope_hash": "sha256:" + "c" * 64,
                    "profile_revision": "workflow-contract-gate-applicability-20260810-r1",
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
                "route_context": {"context": {}},
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
        assert result["failure_code"] == "NODE_ROUTE_MISSING"
        assert result["c1_status"] == "INTEGRATION_PENDING"
        assert result["g6_receipt"] is None


class RecursiveSemanticAdapterTests(unittest.TestCase):
    def test_cli_recursive_mode_calls_canonical_host_and_fails_closed_on_missing_route(self):
        _case_cli_recursive_mode_calls_canonical_host_and_fails_closed_on_missing_route()

    def test_semantic_host_responses_produce_gate_evidence_then_wait_for_real_g6_acceptance(self):
        _case_semantic_host_responses_produce_gate_evidence_then_wait_for_real_g6_acceptance()

    def test_semantic_blocked_maps_to_waiting_without_gate_evidence(self):
        _case_semantic_blocked_maps_to_waiting_without_gate_evidence()

    def test_provider_cannot_select_next_gate_or_route_in_recursive_host_result(self):
        _case_provider_cannot_select_next_gate_or_route_in_recursive_host_result()
