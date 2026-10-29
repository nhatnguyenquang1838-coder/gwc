"""SCRUM-841 selection runs inside the existing canonical Agent Host path."""
from __future__ import annotations

from pathlib import Path
import json
import shutil

from tools.node_architect.ai_agent_adapter import DeterministicFakeProvider
from tools.node_architect.agent_runtime_entrypoint import run_agent_runtime_event, _run_selected_m1_m7_workflow

ROOT = Path(__file__).resolve().parents[1]
BASE = "82a64d30bea55287855d5c591d0b9338f32f450f"
Q0 = "07f34084e0a6e68107bcc1c7e089aa451da5b6ee"
SCOPE = "sha256:a5a477430c7d1ba074db5f59ba16a951f0a04d2a5ef183e66d3d5c44f1496f49"
PLAN = "sha256:04c6eda7000e819b9080146b07dde2441a1ea9e6dec5eadd4701ceb09fa6b233"
REPO = "nhatnguyenquang1838-coder/gwc"
BRANCH = "hermes/SCRUM-841-m1-m7-langgraph-r1"


def _sandbox_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    refs = [
        "AGENTS.md",
        "agents/chatgpt-agent/agent-instructions.md",
        "core/node-architect/node-instructions/repo_delivery/scoped-file-write.node-instruction.yaml",
        "core/node-architect/scrum841-m1-m7-agent-workflow-r1.json",
        "core/node-architect/scrum841-m1-m7-runtime-profile-r1.json",
        "schemas/node-architect/scrum841-m1-m7-agent-workflow.schema.json",
        "schemas/node-architect/scrum841-m1-m7-runtime-profile.schema.json",
    ]
    for ref in refs:
        source = ROOT / ref
        destination = root / ref
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return root


def _route_resolver(**kwargs):
    assert kwargs["context"]["task_id"] == "SCRUM-841"
    assert kwargs["context"]["requested_action"] == "modify_approved_files"
    return {
        "outcome": "ROUTE_SELECTED",
        "reason_code": "ROUTE_SELECTED",
        "route_id": "scrum841-g2-agent-host",
        "current_node": "repo_delivery.scoped-file-write",
        "node_instruction_ref": "core/node-architect/node-instructions/repo_delivery/scoped-file-write.node-instruction.yaml",
        "profile_revision": "profile-r1",
        "graph_revision": "graph-r1",
        "decision_digest": "sha256:" + "d" * 64,
        "authority_granted": False,
        "write_authority_granted": False,
    }


def test_selected_m1_m7_runs_inside_canonical_host_and_holds_without_observer(tmp_path):
    binding = {
        "node_id": "repo_delivery.scoped-file-write",
        "node_version": "1.0.0",
        "node_registry_revision": "registry-r1",
        "implementation_kind": "semantic_tool_callable",
        "implementation_ref": "fixture:underlying-semantic",
        "binding_digest": "sha256:" + "1" * 64,
        "instruction_ref": "core/node-architect/node-instructions/repo_delivery/scoped-file-write.node-instruction.yaml",
        "gates": ["G2_EXECUTION"],
        "entry_contract": [],
        "readback_contract": {"required": True},
        "side_effect_class": "repository_write",
        "authority_requirements": {"gate_authority_required": True, "node_grants_gate_authority": False},
        "checkpoint_contract": {"required": True},
        "next_route_contract": {
            "pass": {"disposition": "stop", "reason": "complete", "next_node": None, "next_action": None, "next_gate": "G2_EXECUTION"},
            "pending": {"disposition": "wait", "reason": "pending", "next_node": "repo_delivery.scoped-file-write", "next_action": "resume", "next_gate": None},
            "blocked": {"disposition": "stop", "reason": "blocked", "next_node": None, "next_action": None, "next_gate": "G2_EXECUTION"},
        },
    }
    operation = {
        "task_id": "SCRUM-841", "repository": REPO,
        "run_id": "g1-841-20261017-1903", "operation_id": "op-841-host-1",
        "activity_id": "tick-841-host-1", "base_sha": BASE, "head_sha": BASE,
        "working_branch": BRANCH, "scope_hash": SCOPE,
        "runtime_plan_digest": PLAN,
    }
    selection = {
        "workflow_id": "scrum841-m1-m7-agent-workflow-r1",
        "operation_envelope": operation,
        "inputs": {"observer_qualified": False, "observer_receipt": None},
        "checkpoint_store_ref": ".gwc/tasks/SCRUM-841/g2/checkpoints/g1-841-20261017-1903.json",
        "checkpoint_expected_revision": 0,
    }
    sandbox_root = _sandbox_root(tmp_path)
    out = run_agent_runtime_event(
        canonical_state={"task_id": "SCRUM-841", "repository": REPO, "branch": BRANCH, "base_sha": BASE, "head_sha": BASE, "scope_hash": SCOPE, "profile_revision": "profile-r1", "graph_revision": "graph-r1", "node_registry_revision": "registry-r1", "policy_revision": "policy-r1", "source_kind": "canonical_agent_gate_state"},
        run_id=operation["run_id"], event_id=operation["operation_id"],
        gate="G2_EXECUTION", requested_action="modify_approved_files",
        scenario="scrum841_m1_m7", workflow_mode="normal",
        input_payload={"objective": "SCRUM-841 M1-M7 workflow", "acceptance_criteria": ["M1 holds without observer"]},
        instruction_refs=("AGENTS.md",), role_overlay_refs=(), required_skill_names=(),
        provider=DeterministicFakeProvider(), provider_registry=None,
        mode="shadow_readonly", authority=None, capability_handlers={},
        readback_handler=lambda *args: {"status": "VERIFIED"},
        evidence_root=tmp_path / "evidence", state=None,
        root=sandbox_root, route_profile={"profile_id": "fixture", "revision": "profile-r1"},
        node_registry={"revision": {"revision_id": "registry-r1"}, "nodes": []},
        graph_registry={"revision": {"revision_id": "graph-r1"}, "edges": []},
        implementation_registry={"status": "PASS", "bindings": [binding]},
        route_context={"task_id": "SCRUM-841", "requested_action": "modify_approved_files"},
        route_resolver=_route_resolver,
        m1_m7_workflow_selection=selection,
    )
    assert out["agent_runtime_wired"] is True
    assert out["status"] == "SEMANTIC_NODE_SUSPENDED"
    assert out["reason_code"] == "OBSERVER_UNQUALIFIED"
    assert out["executed_effects"] == []
    assert out["authority_granted"] is False
    assert out["automatic_gate_advance"] is False
    summary = out["evidence_summary"]
    assert len(summary["paths"]) == 7
    assert Path(summary["events_path"]).is_file()
    assert all(Path(path).is_file() for path in summary["paths"])
    checkpoint_path = sandbox_root / ".gwc/tasks/SCRUM-841/g2/checkpoints/g1-841-20261017-1903.json"
    checkpoint_store = json.loads(checkpoint_path.read_text())
    record = next(iter(checkpoint_store["checkpoints"].values()))
    assert record["state"]["task_id"] == "SCRUM-841"
    assert "browser_url" not in record["state"]
    node_result_path = Path(summary["paths"][2])
    node_result = json.loads(node_result_path.read_text())
    workflow_result = node_result["payload"]["semantic_result"]["workflow_result"]
    assert workflow_result["status"] == "HOLD"
    assert node_result["payload"]["semantic_result"]["checkpoint_persistence"]["outcome"] == "PASS"


def test_checkpoint_resume_reuses_same_operation_and_does_not_duplicate_host_action(tmp_path):
    sandbox_root = _sandbox_root(tmp_path)
    operation = {
        "task_id": "SCRUM-841", "repository": REPO,
        "run_id": "g1-841-20261017-1903", "operation_id": "op-841-resume-1",
        "activity_id": "tick-841-resume-1", "base_sha": BASE, "head_sha": BASE,
        "working_branch": BRANCH, "scope_hash": SCOPE,
        "runtime_plan_digest": PLAN,
        "protocol_version": "dw.taskcontroller.continuation/v1",
        "continuation_ref": "sha256:" + "d" * 64,
        "cursor": {"controller_seq": 20, "executor_seq": 19},
    }
    action = {"action": "modify_approved_files", "idempotency_key": "op-841-resume-1:M5:write-1", "payload_digest": "sha256:" + "e" * 64, "target_ref": "core/node-architect/scrum841-m1-m7-agent-workflow-r1.json"}
    approval_validation = {"outcome": "VALID", "approval_valid": True, "approval_request_ref": "g2_scrum-841_test", "task_id": "SCRUM-841", "repository": REPO, "base_sha": BASE, "head_sha": BASE, "scope_hash": SCOPE, "working_branch": BRANCH, "risk_class": "R2", "authorized_actions": [action["action"]], "validation_digest": "sha256:" + "f" * 64, "execution_authority_granted": False, "merge_authority_granted": False, "deployment_authority_granted": False, "production_authority_granted": False}
    activation = {"artifact_type": "g2-activation-receipt", "activation_state": "ACTIVE", "approval_request_id": "g2_scrum-841_test", "approval_validation": approval_validation, "approval_validation_digest": approval_validation["validation_digest"], "approval_request_actor_id": "Nhat Nguyen Quang", "validated_actor_id": "Nhat Nguyen Quang", "envelope_digest": "sha256:" + "1" * 64, "expires_at": "2099-12-31T23:59:59Z", "execution_started": False, "task_id": "SCRUM-841", "repository": REPO, "run_id": operation["run_id"], "branch": BRANCH, "base_sha": BASE, "head_sha": BASE, "scope_hash": SCOPE, "risk_class": "R2", "gate": "G2_EXECUTION", "authorized_actions": [action["action"]], "authorized_paths": [action["target_ref"]]}
    selection = {
        "workflow_id": "scrum841-m1-m7-agent-workflow-r1",
        "operation_envelope": operation,
        "inputs": {"observer_qualified": True, "observer_receipt": {**operation, "classification": "CLEAR"}, "action_request": action, "g2_activation_receipt": activation, "prior_host_action_requests": []},
        "checkpoint_store_ref": ".gwc/tasks/SCRUM-841/g2/checkpoints/g1-841-20261017-1903.json",
        "checkpoint_expected_revision": 0,
    }
    canonical = {"task_id": "SCRUM-841", "repository": REPO, "branch": BRANCH, "base_sha": BASE, "head_sha": BASE, "scope_hash": SCOPE}
    binding = {"next_route_contract": {"pending": {"disposition": "wait", "reason": "pending", "next_node": "repo_delivery.scoped-file-write", "next_action": "resume", "next_gate": None}, "blocked": {"disposition": "stop", "reason": "blocked", "next_node": None, "next_action": None, "next_gate": "G2_EXECUTION"}}}
    first = _run_selected_m1_m7_workflow(selection=selection, canonical_state=canonical, current_binding=binding, root=sandbox_root)
    assert first["workflow_result"]["reason_code"] == "M5_HOST_ACTION_REQUESTED"
    assert len(first["workflow_result"]["host_action_requests"]) == 1
    selection2 = {**selection, "checkpoint_expected_revision": 1}
    second = _run_selected_m1_m7_workflow(selection=selection2, canonical_state=canonical, current_binding=binding, root=sandbox_root)
    assert second["workflow_result"]["reason_code"] == "M5_ACTION_ALREADY_REQUESTED"
    assert second["workflow_result"]["host_action_requests"] == []
    assert second["checkpoint_persistence"]["outcome"] == "IDEMPOTENT_REPLAY"
    store = json.loads((sandbox_root/selection["checkpoint_store_ref"]).read_text())
    assert store["revision"] == 1
    checkpoint = next(iter(store["checkpoints"].values()))
    assert checkpoint["run_id"] == operation["run_id"]
    assert checkpoint["state"]["idempotency_keys"] == [action["idempotency_key"]]
    host_request = {**action, "task_id": "SCRUM-841", "repository": REPO, "run_id": operation["run_id"], "operation_id": operation["operation_id"], "activity_id": operation["activity_id"], "base_sha": BASE, "head_sha": BASE, "working_branch": BRANCH, "scope_hash": SCOPE, "runtime_plan_digest": PLAN}
    host_receipt = {**host_request, "status": "VERIFIED", "readback_status": "VERIFIED", "readback_target": action["target_ref"], "readback_digest": "sha256:" + "2" * 64, "validation_outcome": "PASS", "validation_digest": "sha256:" + "3" * 64}
    selection3 = {**selection, "inputs": {**selection["inputs"], "host_action_receipt": host_receipt}, "checkpoint_expected_revision": 1}
    third = _run_selected_m1_m7_workflow(selection=selection3, canonical_state=canonical, current_binding=binding, root=sandbox_root)
    assert third["workflow_result"]["current_activity"] == "M7"
    assert third["workflow_result"]["activity_results"]["M6"]["status"] == "PASS"
    assert third["workflow_result"]["host_action_requests"] == []
    assert third["checkpoint_persistence"]["outcome"] == "PASS"
    resumed_store = json.loads((sandbox_root/selection["checkpoint_store_ref"]).read_text())
    resumed_checkpoint = next(iter(resumed_store["checkpoints"].values()))
    assert resumed_store["revision"] == 2
    assert resumed_checkpoint["state"]["current_activity"] == "M7"
