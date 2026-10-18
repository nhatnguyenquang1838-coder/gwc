"""SCRUM-841 host request/receipt contract for M5-M7 (P6).

Verifies the graph emits only data-only typed host-action requests and exact
host receipt reconciliation: at most one request per idempotency key, no
duplicate on resume, exact M6 readback/validator evidence, and M7 mailbox +
settlement requests only under a qualified protocol capability.
"""
from __future__ import annotations

from tools.node_architect.m1_m7_agent_workflow import (
    M1_M7_SOURCE_SHA256,
    build_m1_m7_graph,
)

REPOSITORY = "nhatnguyenquang1838-coder/gwc"
BASE = "82a64d30bea55287855d5c591d0b9338f32f450f"
BRANCH = "hermes/SCRUM-841-m1-m7-langgraph-r1"
SCOPE = "sha256:" + "a" * 64
PLAN = "sha256:" + "b" * 64
SOURCE = M1_M7_SOURCE_SHA256


def _contracts():
    manifest = {
        "schema_version": "1.0",
        "artifact_type": "scrum841-m1-m7-workflow",
        "workflow_id": "scrum841-m1-m7-agent-workflow-r1",
        "task_id": "SCRUM-841",
        "source_sha256": SOURCE,
        "runtime_plan_digest": PLAN,
        "allowed_activities": ["M1", "M2", "M3", "M4", "M5", "M6", "M7"],
        "edges": [
            {"from": "M1", "to": "M2"}, {"from": "M2", "to": "M3"},
            {"from": "M3", "to": "M4"}, {"from": "M4", "to": "M5"},
            {"from": "M5", "to": "M6"}, {"from": "M6", "to": "M7"},
        ],
    }
    profile = {
        "schema_version": "1.0", "artifact_type": "scrum841-m1-m7-runtime-profile",
        "task_id": "SCRUM-841", "repository": REPOSITORY, "base_sha": BASE,
        "target_sha": "07f34084e0a6e68107bcc1c7e089aa451da5b6ee",
        "working_branch": BRANCH, "scope_hash": SCOPE,
        "runtime_plan_digest": PLAN, "workflow_id": manifest["workflow_id"],
        "activity_source_sha256": SOURCE, "risk_class": "R2",
        "authorized_paths": ["core/node-architect/scrum841-m1-m7-agent-workflow-r1.json"],
        "authorized_actions": ["create_guarded_branch_or_worktree", "modify_approved_files", "run_sandboxed_validation"],
        "q0_authority_reused": False, "native_loop_owner": "hermes_host",
    }
    return manifest, profile


def _operation(op_id: str):
    return {
        "task_id": "SCRUM-841", "repository": REPOSITORY,
        "run_id": "g1-841-host-run", "operation_id": op_id,
        "activity_id": f"tick-{op_id}", "base_sha": BASE, "head_sha": BASE,
        "working_branch": BRANCH, "scope_hash": SCOPE,
        "runtime_plan_digest": PLAN,
        "protocol_version": "dw.taskcontroller.continuation/v1",
        "continuation_ref": "sha256:" + "d" * 64,
        "cursor": {"controller_seq": 20, "executor_seq": 19},
    }


def _activation(operation, action):
    validation = {
        "artifact_type": "gate-approval-validation", "outcome": "VALID",
        "approval_valid": True, "approval_request_ref": "g2_scrum-841_host",
        "task_id": "SCRUM-841", "repository": REPOSITORY,
        "base_sha": BASE, "head_sha": BASE, "scope_hash": SCOPE,
        "working_branch": BRANCH, "risk_class": "R2",
        "authorized_actions": [action["action"]],
        "validation_digest": "sha256:" + "f" * 64,
        "execution_authority_granted": False, "merge_authority_granted": False,
        "deployment_authority_granted": False, "production_authority_granted": False,
    }
    return {
        "artifact_type": "g2-activation-receipt", "activation_state": "ACTIVE",
        "approval_request_id": "g2_scrum-841_host", "approval_validation": validation,
        "approval_validation_digest": validation["validation_digest"],
        "approval_request_actor_id": "Nhat Nguyen Quang",
        "validated_actor_id": "Nhat Nguyen Quang",
        "envelope_digest": "sha256:" + "1" * 64,
        "expires_at": "2099-12-31T23:59:59Z", "execution_started": False,
        "task_id": "SCRUM-841", "repository": REPOSITORY,
        "run_id": operation["run_id"], "branch": BRANCH,
        "base_sha": BASE, "head_sha": BASE, "scope_hash": SCOPE,
        "risk_class": "R2", "gate": "G2_EXECUTION",
        "authorized_actions": [action["action"]],
        "authorized_paths": [action.get("target_ref")] if action.get("target_ref") else [],
    }


def _graph():
    manifest, profile = _contracts()
    return build_m1_m7_graph(workflow_manifest=manifest, runtime_profile=profile, activity_source_sha256=SOURCE)


def test_m5_at_most_one_data_only_host_action_request_per_idempotency_key():
    graph = _graph()
    operation = _operation("op-841-h1")
    action = {"action": "modify_approved_files", "idempotency_key": "op-841-h1:M5:write-1", "payload_digest": "sha256:" + "e" * 64, "target_ref": "core/node-architect/scrum841-m1-m7-agent-workflow-r1.json"}
    authority = _activation(operation, action)
    result = graph.invoke({
        "operation_envelope": operation,
        "inputs": {"observer_qualified": True, "observer_receipt": {**operation, "classification": "CLEAR"}, "action_request": action, "g2_activation_receipt": authority, "prior_host_action_requests": []},
        "host_action_requests": [], "settlement_requests": [],
    })
    assert result["status"] == "WAIT"
    assert result["reason_code"] == "M5_HOST_ACTION_REQUESTED"
    assert len(result["host_action_requests"]) == 1
    request = result["host_action_requests"][0]
    assert request["request_type"] == "host_action_request"
    assert request["idempotency_key"] == action["idempotency_key"]
    assert request["effect_performed"] is False
    assert request["authority_granted"] is False
    assert result["executed_effects"] == []


def test_resume_with_prior_request_does_not_duplicate():
    graph = _graph()
    operation = _operation("op-841-h2")
    action = {"action": "modify_approved_files", "idempotency_key": "op-841-h2:M5:write-1", "payload_digest": "sha256:" + "e" * 64, "target_ref": "core/node-architect/scrum841-m1-m7-agent-workflow-r1.json"}
    authority = _activation(operation, action)
    prior = [{"idempotency_key": action["idempotency_key"]}]
    result = graph.invoke({
        "operation_envelope": operation,
        "inputs": {"observer_qualified": True, "observer_receipt": {**operation, "classification": "CLEAR"}, "action_request": action, "g2_activation_receipt": authority, "prior_host_action_requests": prior},
        "host_action_requests": [], "settlement_requests": [],
    })
    assert result["status"] == "WAIT"
    assert result["reason_code"] == "M5_ACTION_ALREADY_REQUESTED"
    assert result["host_action_requests"] == []


def test_m5_rejects_host_receipt_without_prior_request():
    graph = _graph()
    operation = _operation("op-841-h3")
    action = {"action": "modify_approved_files", "idempotency_key": "op-841-h3:M5:write-1", "payload_digest": "sha256:" + "e" * 64, "target_ref": "core/node-architect/scrum841-m1-m7-agent-workflow-r1.json"}
    authority = _activation(operation, action)
    receipt = {"idempotency_key": action["idempotency_key"], "status": "VERIFIED"}
    result = graph.invoke({
        "operation_envelope": operation,
        "inputs": {"observer_qualified": True, "observer_receipt": {**operation, "classification": "CLEAR"}, "action_request": action, "g2_activation_receipt": authority, "prior_host_action_requests": [], "host_action_receipt": receipt},
        "host_action_requests": [], "settlement_requests": [],
    })
    assert result["status"] == "HOLD"
    assert result["reason_code"] == "M5_HOST_RECEIPT_WITHOUT_REQUEST"
    assert result["host_action_requests"] == []


def test_m6_exact_readback_mismatch_fails_closed():
    graph = _graph()
    operation = _operation("op-841-h4")
    action = {"action": "modify_approved_files", "idempotency_key": "op-841-h4:M5:write-1", "payload_digest": "sha256:" + "e" * 64, "target_ref": "core/node-architect/scrum841-m1-m7-agent-workflow-r1.json"}
    authority = _activation(operation, action)
    host_request = {**action, "task_id": "SCRUM-841", "repository": REPOSITORY, "run_id": operation["run_id"], "operation_id": operation["operation_id"], "activity_id": operation["activity_id"], "base_sha": BASE, "head_sha": BASE, "working_branch": BRANCH, "scope_hash": SCOPE, "runtime_plan_digest": PLAN}
    host_receipt = {**host_request, "status": "VERIFIED", "readback_status": "VERIFIED", "readback_target": "WRONG-TARGET", "readback_digest": "sha256:" + "2" * 64, "validation_outcome": "PASS", "validation_digest": "sha256:" + "3" * 64}
    result = graph.invoke({
        "operation_envelope": operation,
        "inputs": {"observer_qualified": True, "observer_receipt": {**operation, "classification": "CLEAR"}, "action_request": action, "g2_activation_receipt": authority, "prior_host_action_requests": [host_request], "host_action_receipt": host_receipt},
        "host_action_requests": [], "settlement_requests": [],
    })
    assert result["status"] == "HOLD"
    assert result["reason_code"] == "M6_EXACT_READBACK_MISMATCH"


def test_m6_verified_receipt_produces_exact_evidence():
    graph = _graph()
    operation = _operation("op-841-h5")
    action = {"action": "modify_approved_files", "idempotency_key": "op-841-h5:M5:write-1", "payload_digest": "sha256:" + "e" * 64, "target_ref": "core/node-architect/scrum841-m1-m7-agent-workflow-r1.json"}
    authority = _activation(operation, action)
    host_request = {**action, "task_id": "SCRUM-841", "repository": REPOSITORY, "run_id": operation["run_id"], "operation_id": operation["operation_id"], "activity_id": operation["activity_id"], "base_sha": BASE, "head_sha": BASE, "working_branch": BRANCH, "scope_hash": SCOPE, "runtime_plan_digest": PLAN}
    host_receipt = {**host_request, "status": "VERIFIED", "readback_status": "VERIFIED", "readback_target": action["target_ref"], "readback_digest": "sha256:" + "2" * 64, "validation_outcome": "PASS", "validation_digest": "sha256:" + "3" * 64}
    result = graph.invoke({
        "operation_envelope": operation,
        "inputs": {"observer_qualified": True, "observer_receipt": {**operation, "classification": "CLEAR"}, "action_request": action, "g2_activation_receipt": authority, "prior_host_action_requests": [host_request], "host_action_receipt": host_receipt},
        "host_action_requests": [], "settlement_requests": [],
    })
    assert result["activity_results"]["M6"]["status"] == "PASS"
    assert result["activity_results"]["M6"]["readback_digest"] == host_receipt["readback_digest"]
    assert result["host_action_requests"] == []
    assert result["executed_effects"] == []


def test_m7_qualified_mailbox_and_settlement_are_single_data_only_requests():
    graph = _graph()
    operation = _operation("op-841-h6")
    action = {"action": "modify_approved_files", "idempotency_key": "op-841-h6:M5:write-1", "payload_digest": "sha256:" + "e" * 64, "target_ref": "core/node-architect/scrum841-m1-m7-agent-workflow-r1.json"}
    authority = _activation(operation, action)
    host_request = {**action, "task_id": "SCRUM-841", "repository": REPOSITORY, "run_id": operation["run_id"], "operation_id": operation["operation_id"], "activity_id": operation["activity_id"], "base_sha": BASE, "head_sha": BASE, "working_branch": BRANCH, "scope_hash": SCOPE, "runtime_plan_digest": PLAN}
    host_receipt = {**host_request, "status": "VERIFIED", "readback_status": "VERIFIED", "readback_target": action["target_ref"], "readback_digest": "sha256:" + "2" * 64, "validation_outcome": "PASS", "validation_digest": "sha256:" + "3" * 64}
    capability = {**operation, "artifact_type": "native-loop-capability-receipt", "qualified": True, "native_loop_owner": "hermes_host", "settlement_allowed": True, "receipt_digest": "sha256:" + "4" * 64}
    mailbox_capability = {**operation, "artifact_type": "m7-mailbox-notification-capability-receipt", "qualified": True, "single_executor_mailbox": True, "mailbox_patch_allowed": True, "controller_notification_allowed": True, "executor_mailbox_ref": "taskcontroller://executor/current", "controller_notification_target": "controller://bound", "receipt_digest": "sha256:" + "5" * 64}
    result = graph.invoke({
        "operation_envelope": operation,
        "inputs": {
            "observer_qualified": True, "observer_receipt": {**operation, "classification": "CLEAR"},
            "action_request": action, "g2_activation_receipt": authority,
            "prior_host_action_requests": [host_request], "host_action_receipt": host_receipt,
            "settlement_capability_receipt": capability, "mailbox_notification_capability": mailbox_capability,
        },
        "host_action_requests": [], "settlement_requests": [],
    })
    assert result["status"] == "WAIT"
    assert result["reason_code"] == "M7_SETTLEMENT_REQUESTED"
    assert len(result["host_action_requests"]) == 1
    assert result["host_action_requests"][0]["action"] == "m7_executor_mailbox_patch_readback_controller_notify"
    assert result["host_action_requests"][0]["effect_performed"] is False
    assert len(result["settlement_requests"]) == 1
    settlement = result["settlement_requests"][0]
    assert settlement["requested_settlement"] == "complete"
    assert settlement["requires_host_readback"] is True
    assert settlement["settled"] is False
    assert settlement["authority_granted"] is False
    assert result["executed_effects"] == []
    assert "complete_tick" not in result