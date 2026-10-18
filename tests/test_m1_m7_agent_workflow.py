"""SCRUM-841 LangGraph workflow integration tests (TDD, slice 1: M1 HOLD)."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.node_architect.m1_m7_agent_workflow import (
    M1_M7_SOURCE_SHA256,
    WorkflowContractError,
    build_m1_m7_graph,
    load_m1_m7_contracts,
)

REPOSITORY = "nhatnguyenquang1838-coder/gwc"
BASE = "82a64d30bea55287855d5c591d0b9338f32f450f"
BRANCH = "hermes/SCRUM-841-m1-m7-langgraph-r1"
SCOPE = "sha256:" + "a" * 64
PLAN = "sha256:" + "b" * 64
SOURCE = "sha256:6fa893e8224f824e562945cca8b7d66d382d060b1308bd0dbd481fdd612fa9c3"


def _activation_receipt(operation, action):
    validation = {
        "artifact_type": "gate-approval-validation",
        "outcome": "VALID",
        "approval_valid": True,
        "approval_request_ref": "g2_scrum-841_test",
        "task_id": "SCRUM-841", "repository": REPOSITORY,
        "base_sha": BASE, "head_sha": BASE, "scope_hash": SCOPE,
        "working_branch": BRANCH, "risk_class": "R2",
        "authorized_actions": [action["action"]],
        "validation_digest": "sha256:" + "f" * 64,
        "execution_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }
    return {
        "artifact_type": "g2-activation-receipt",
        "activation_state": "ACTIVE",
        "approval_request_id": "g2_scrum-841_test",
        "approval_validation": validation,
        "approval_validation_digest": validation["validation_digest"],
        "approval_request_actor_id": "Nhat Nguyen Quang",
        "validated_actor_id": "Nhat Nguyen Quang",
        "envelope_digest": "sha256:" + "1" * 64,
        "expires_at": "2099-12-31T23:59:59Z",
        "execution_started": False,
        "task_id": "SCRUM-841", "repository": REPOSITORY,
        "run_id": operation["run_id"], "branch": BRANCH,
        "base_sha": BASE, "head_sha": BASE, "scope_hash": SCOPE,
        "risk_class": "R2",
        "gate": "G2_EXECUTION", "authorized_actions": [action["action"]],
        "authorized_paths": [action.get("target_ref")] if action.get("target_ref") else [],
    }


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
            {"from": "M1", "to": "M2"},
            {"from": "M2", "to": "M3"},
            {"from": "M3", "to": "M4"},
            {"from": "M4", "to": "M5"},
            {"from": "M5", "to": "M6"},
            {"from": "M6", "to": "M7"},
        ],
    }
    profile = {
        "schema_version": "1.0",
        "artifact_type": "scrum841-m1-m7-runtime-profile",
        "task_id": "SCRUM-841",
        "repository": REPOSITORY,
        "base_sha": BASE,
        "target_sha": "07f34084e0a6e68107bcc1c7e089aa451da5b6ee",
        "working_branch": BRANCH,
        "scope_hash": SCOPE,
        "runtime_plan_digest": PLAN,
        "workflow_id": manifest["workflow_id"],
        "activity_source_sha256": SOURCE,
        "risk_class": "R2",
        "authorized_paths": ["core/node-architect/scrum841-m1-m7-agent-workflow-r1.json"],
        "authorized_actions": ["create_guarded_branch_or_worktree", "modify_approved_files", "run_sandboxed_validation"],
        "q0_authority_reused": False,
        "native_loop_owner": "hermes_host",
    }
    return manifest, profile


def test_unqualified_m1_observer_holds_without_polling_or_host_requests():
    manifest, profile = _contracts()
    graph = build_m1_m7_graph(
        workflow_manifest=manifest,
        runtime_profile=profile,
        activity_source_sha256=SOURCE,
    )
    calls = []
    result = graph.invoke({
        "operation_envelope": {
            "task_id": "SCRUM-841",
            "repository": REPOSITORY,
            "run_id": "g1-841-test-run",
            "operation_id": "op-841-001",
            "activity_id": "tick-841-001",
            "base_sha": BASE,
            "head_sha": BASE,
            "working_branch": BRANCH,
            "scope_hash": SCOPE,
            "runtime_plan_digest": PLAN,
        },
        "inputs": {"observer_qualified": False, "observer_receipt": None},
        "host_action_requests": [],
        "settlement_requests": [],
    })
    assert result["status"] == "HOLD"
    assert result["reason_code"] == "OBSERVER_UNQUALIFIED"
    assert result["current_activity"] == "M1"
    assert result["host_action_requests"] == []
    assert result["settlement_requests"] == []
    assert calls == []


def test_m1_blocked_classification_stops_before_later_activities():
    manifest, profile = _contracts()
    graph = build_m1_m7_graph(workflow_manifest=manifest, runtime_profile=profile, activity_source_sha256=SOURCE)
    operation = {
        "task_id": "SCRUM-841", "repository": REPOSITORY,
        "run_id": "g1-841-test-run", "operation_id": "op-841-blocked",
        "activity_id": "tick-841-blocked", "base_sha": BASE, "head_sha": BASE,
        "working_branch": BRANCH, "scope_hash": SCOPE,
        "runtime_plan_digest": PLAN,
    }
    result = graph.invoke({
        "operation_envelope": operation,
        "inputs": {"observer_qualified": True, "observer_receipt": {**operation, "classification": "BLOCKED"}},
        "host_action_requests": [], "settlement_requests": [],
    })
    assert result["status"] == "HOLD"
    assert result["reason_code"] == "M1_MAILBOX_BLOCKED"
    assert result["current_activity"] == "M1"
    assert "M2" not in result.get("activity_results", {})
    assert result["host_action_requests"] == []
    assert result["settlement_requests"] == []



def test_unknown_activity_or_edge_is_rejected_before_graph_compilation():
    manifest, profile = _contracts()
    manifest["edges"].append({"from": "M1", "to": "M8"})
    with pytest.raises(WorkflowContractError, match="UNKNOWN_ACTIVITY_EDGE"):
        build_m1_m7_graph(
            workflow_manifest=manifest,
            runtime_profile=profile,
            activity_source_sha256=SOURCE,
        )


def test_on_disk_workflow_and_runtime_profile_are_closed_and_g1_bound():
    repository_root = Path(__file__).resolve().parents[1]
    manifest, profile = load_m1_m7_contracts(repository_root)
    assert manifest["source_sha256"] == M1_M7_SOURCE_SHA256
    assert profile["task_id"] == "SCRUM-841"
    assert profile["base_sha"] == "82a64d30bea55287855d5c591d0b9338f32f450f"
    assert profile["target_sha"] == "07f34084e0a6e68107bcc1c7e089aa451da5b6ee"
    assert profile["scope_hash"] == "sha256:a5a477430c7d1ba074db5f59ba16a951f0a04d2a5ef183e66d3d5c44f1496f49"
    assert profile["runtime_plan_digest"] == "sha256:04c6eda7000e819b9080146b07dde2441a1ea9e6dec5eadd4701ceb09fa6b233"
    assert profile["max_children"] == 0
    assert profile["authority_granted"] is False



def test_checkpoint_forbidden_keys_match_manifest_patterns():
    """Manifest forbids `same:N`/`SAME:XX` patterns; checkpoint must fail closed."""
    manifest, profile = _contracts()
    graph = build_m1_m7_graph(
        workflow_manifest=manifest,
        runtime_profile=profile,
        activity_source_sha256=SOURCE,
    )
    operation = {
        "task_id": "SCRUM-841", "repository": REPOSITORY,
        "run_id": "g1-841-test-run", "operation_id": "op-841-010",
        "activity_id": "tick-841-010", "base_sha": BASE, "head_sha": BASE,
        "working_branch": BRANCH, "scope_hash": SCOPE,
        "runtime_plan_digest": PLAN,
        "protocol_version": "dw.taskcontroller.continuation/v1",
        "continuation_ref": "sha256:" + "d" * 64,
        "cursor": {"controller_seq": 21, "executor_seq": 20},
    }
    for forbidden_key in ("same:N", "SAME:XX"):
        result = graph.invoke({
            "operation_envelope": operation,
            "checkpoint_projection": {
                **operation,
                "current_activity": "M3",
                forbidden_key: "same:4",
            },
            "inputs": {"observer_qualified": True},
            "host_action_requests": [], "settlement_requests": [],
        })
        assert result["status"] == "BLOCKED"
        assert result["reason_code"] == "CHECKPOINT_FORBIDDEN_BINDING"
        assert result["authority_granted"] is False


def test_m2_holds_on_observed_mailbox_base_drift():
    manifest, profile = _contracts()
    graph = build_m1_m7_graph(
        workflow_manifest=manifest,
        runtime_profile=profile,
        activity_source_sha256=SOURCE,
    )
    operation = {
        "task_id": "SCRUM-841",
        "repository": REPOSITORY,
        "run_id": "g1-841-test-run",
        "operation_id": "op-841-001",
        "activity_id": "tick-841-001",
        "base_sha": BASE,
        "head_sha": BASE,
        "working_branch": BRANCH,
        "scope_hash": SCOPE,
        "runtime_plan_digest": PLAN,
        "protocol_version": "dw.taskcontroller.continuation/v1",
        "continuation_ref": "sha256:" + "d" * 64,
        "cursor": {"controller_seq": 8, "executor_seq": 7},
    }
    receipt = {
        **operation,
        "base_sha": "c" * 40,
        "protocol_version": "dw.taskcontroller.continuation/v1",
        "continuation_ref": "sha256:" + "d" * 64,
        "cursor": {"controller_seq": 8, "executor_seq": 7},
        "classification": "CLEAR",
    }
    result = graph.invoke({
        "operation_envelope": operation,
        "inputs": {"observer_qualified": True, "observer_receipt": receipt},
        "host_action_requests": [],
        "settlement_requests": [],
    })
    assert result["status"] == "HOLD"
    assert result["reason_code"] == "M2_BINDING_MISMATCH"
    assert result["current_activity"] == "M2"
    assert result["host_action_requests"] == []
    assert result["settlement_requests"] == []


def test_m3_records_analyzer_not_declared_without_child_dispatch():
    manifest, profile = _contracts()
    graph = build_m1_m7_graph(
        workflow_manifest=manifest,
        runtime_profile=profile,
        activity_source_sha256=SOURCE,
    )
    operation = {
        "task_id": "SCRUM-841",
        "repository": REPOSITORY,
        "run_id": "g1-841-test-run",
        "operation_id": "op-841-002",
        "activity_id": "tick-841-002",
        "base_sha": BASE,
        "head_sha": BASE,
        "working_branch": BRANCH,
        "scope_hash": SCOPE,
        "runtime_plan_digest": PLAN,
        "protocol_version": "dw.taskcontroller.continuation/v1",
        "continuation_ref": "sha256:" + "d" * 64,
        "cursor": {"controller_seq": 12, "executor_seq": 11},
    }
    observer_receipt = {**operation, "classification": "PENDING"}
    red_team_receipt = {
        **operation,
        "status": "VERIFIED",
        "read_only": True,
        "result_digest": "sha256:" + "e" * 64,
    }
    result = graph.invoke({
        "operation_envelope": operation,
        "inputs": {
            "observer_qualified": True,
            "observer_receipt": observer_receipt,
            "red_team_receipt": red_team_receipt,
            "typed_read_only_child_contract": None,
            "max_children": 0,
        },
        "host_action_requests": [],
        "settlement_requests": [],
    })
    assert result["activity_results"]["M3"]["analyzer_disposition"] == "ANALYZER_NOT_DECLARED"
    assert result["child_dispatch_requests"] == []
    assert result["host_action_requests"] == []
    assert result["settlement_requests"] == []
    assert result["authority_granted"] is False


def test_m4_emits_one_bound_controller_exchange_request_without_authority():
    manifest, profile = _contracts()
    graph = build_m1_m7_graph(
        workflow_manifest=manifest,
        runtime_profile=profile,
        activity_source_sha256=SOURCE,
    )
    operation = {
        "task_id": "SCRUM-841", "repository": REPOSITORY,
        "run_id": "g1-841-test-run", "operation_id": "op-841-003",
        "activity_id": "tick-841-003", "base_sha": BASE, "head_sha": BASE,
        "working_branch": BRANCH, "scope_hash": SCOPE,
        "runtime_plan_digest": PLAN,
        "protocol_version": "dw.taskcontroller.continuation/v1",
        "continuation_ref": "sha256:" + "d" * 64,
        "cursor": {"controller_seq": 13, "executor_seq": 12},
    }
    controller_binding = {**operation, "blocker_key": "review-conflict-1"}
    result = graph.invoke({
        "operation_envelope": operation,
        "inputs": {
            "observer_qualified": True,
            "observer_receipt": {**operation, "classification": "CONFLICT"},
            "controller_blocker": True,
            "controller_exchange_binding": controller_binding,
            "prior_controller_exchange_requests": [],
        },
        "host_action_requests": [],
        "settlement_requests": [],
    })
    requests = result["controller_exchange_requests"]
    assert len(requests) == 1
    assert requests[0]["task_id"] == "SCRUM-841"
    assert requests[0]["operation_id"] == operation["operation_id"]
    assert requests[0]["blocker_key"] == "review-conflict-1"
    assert requests[0]["scope_hash"] == SCOPE
    assert requests[0]["authority_granted"] is False
    assert result["authority_granted"] is False
    assert result["host_action_requests"] == []
    assert result["settlement_requests"] == []


def test_m4_does_not_duplicate_a_reconciliation_request_on_resume():
    manifest, profile = _contracts()
    graph = build_m1_m7_graph(
        workflow_manifest=manifest,
        runtime_profile=profile,
        activity_source_sha256=SOURCE,
    )
    operation = {
        "task_id": "SCRUM-841", "repository": REPOSITORY,
        "run_id": "g1-841-test-run", "operation_id": "op-841-004",
        "activity_id": "tick-841-004", "base_sha": BASE, "head_sha": BASE,
        "working_branch": BRANCH, "scope_hash": SCOPE,
        "runtime_plan_digest": PLAN,
        "protocol_version": "dw.taskcontroller.continuation/v1",
        "continuation_ref": "sha256:" + "d" * 64,
        "cursor": {"controller_seq": 14, "executor_seq": 13},
    }
    binding = {**operation, "blocker_key": "review-conflict-2"}
    key = "op-841-004:M4:review-conflict-2"
    result = graph.invoke({
        "operation_envelope": operation,
        "inputs": {
            "observer_qualified": True,
            "observer_receipt": {**operation, "classification": "CONFLICT"},
            "controller_blocker": True,
            "controller_exchange_binding": binding,
            "prior_controller_exchange_requests": [{"idempotency_key": key}],
        },
        "host_action_requests": [],
        "settlement_requests": [],
    })
    assert result["status"] == "WAIT"
    assert result["reason_code"] == "M4_RECONCILIATION_ALREADY_REQUESTED"
    assert result["controller_exchange_requests"] == []
    assert result["authority_granted"] is False


def test_m5_rejects_approval_validated_for_another_actor():
    manifest, profile = _contracts()
    graph = build_m1_m7_graph(workflow_manifest=manifest, runtime_profile=profile, activity_source_sha256=SOURCE)
    operation = {
        "task_id": "SCRUM-841", "repository": REPOSITORY,
        "run_id": "g1-841-test-run", "operation_id": "op-841-011",
        "activity_id": "tick-841-011", "base_sha": BASE, "head_sha": BASE,
        "working_branch": BRANCH, "scope_hash": SCOPE,
        "runtime_plan_digest": PLAN,
        "protocol_version": "dw.taskcontroller.continuation/v1",
        "continuation_ref": "sha256:" + "d" * 64,
        "cursor": {"controller_seq": 15, "executor_seq": 14},
    }
    action = {
        "action": "modify_approved_files",
        "idempotency_key": "op-841-011:M5:write-1",
        "payload_digest": "sha256:" + "e" * 64,
        "target_ref": "core/node-architect/scrum841-m1-m7-agent-workflow-r1.json",
    }
    authority = _activation_receipt(operation, action)
    authority["validated_actor_id"] = "different-human"
    result = graph.invoke({
        "operation_envelope": operation,
        "inputs": {
            "observer_qualified": True,
            "observer_receipt": {**operation, "classification": "CLEAR"},
            "action_request": action,
            "g2_activation_receipt": authority,
            "prior_host_action_requests": [],
        },
    })
    assert result["status"] == "HOLD"
    assert result["reason_code"] == "M5_APPROVAL_VALIDATION_BINDING_MISMATCH"
    assert result["host_action_requests"] == []
    assert result["authority_granted"] is False


def test_m5_emits_one_bound_data_only_host_action_request():
    manifest, profile = _contracts()
    graph = build_m1_m7_graph(
        workflow_manifest=manifest,
        runtime_profile=profile,
        activity_source_sha256=SOURCE,
    )
    operation = {
        "task_id": "SCRUM-841", "repository": REPOSITORY,
        "run_id": "g1-841-test-run", "operation_id": "op-841-005",
        "activity_id": "tick-841-005", "base_sha": BASE, "head_sha": BASE,
        "working_branch": BRANCH, "scope_hash": SCOPE,
        "runtime_plan_digest": PLAN,
        "protocol_version": "dw.taskcontroller.continuation/v1",
        "continuation_ref": "sha256:" + "d" * 64,
        "cursor": {"controller_seq": 15, "executor_seq": 14},
    }
    action = {
        "action": "modify_approved_files",
        "idempotency_key": "op-841-005:M5:write-1",
        "payload_digest": "sha256:" + "e" * 64,
        "target_ref": "core/node-architect/scrum841-m1-m7-agent-workflow-r1.json",
    }
    authority = _activation_receipt(operation, action)
    result = graph.invoke({
        "operation_envelope": operation,
        "inputs": {
            "observer_qualified": True,
            "observer_receipt": {**operation, "classification": "CLEAR"},
            "action_request": action,
            "g2_activation_receipt": authority,
            "prior_host_action_requests": [],
        },
        "host_action_requests": [], "settlement_requests": [],
    })
    requests = result["host_action_requests"]
    assert result["status"] == "WAIT"
    assert len(requests) == 1
    assert requests[0]["action"] == action["action"]
    assert requests[0]["idempotency_key"] == action["idempotency_key"]
    assert requests[0]["payload_digest"] == action["payload_digest"]
    assert requests[0]["authority_ref"] == authority["envelope_digest"]
    assert result["executed_effects"] == []
    assert result["authority_granted"] is False
    assert result["settlement_requests"] == []


def test_m5_holds_on_unknown_prior_effect_without_duplicate_request():
    manifest, profile = _contracts()
    graph = build_m1_m7_graph(workflow_manifest=manifest, runtime_profile=profile, activity_source_sha256=SOURCE)
    operation = {
        "task_id": "SCRUM-841", "repository": REPOSITORY,
        "run_id": "g1-841-test-run", "operation_id": "op-841-006",
        "activity_id": "tick-841-006", "base_sha": BASE, "head_sha": BASE,
        "working_branch": BRANCH, "scope_hash": SCOPE,
        "runtime_plan_digest": PLAN,
        "protocol_version": "dw.taskcontroller.continuation/v1",
        "continuation_ref": "sha256:" + "d" * 64,
        "cursor": {"controller_seq": 16, "executor_seq": 15},
    }
    action = {"action": "modify_approved_files", "idempotency_key": "op-841-006:M5:write-1", "payload_digest": "sha256:" + "e" * 64}
    authority = _activation_receipt(operation, action)
    result = graph.invoke({
        "operation_envelope": operation,
        "inputs": {"observer_qualified": True, "observer_receipt": {**operation, "classification": "CLEAR"}, "action_request": action, "g2_activation_receipt": authority, "prior_host_action_requests": [], "prior_effect_outcome_unknown": True},
        "host_action_requests": [], "settlement_requests": [],
    })
    assert result["status"] == "HOLD"
    assert result["reason_code"] == "M5_UNKNOWN_EFFECT_REQUIRES_RECONCILIATION"
    assert result["host_action_requests"] == []
    assert result["executed_effects"] == []


def test_m6_requires_exact_host_readback_and_validation_receipt():
    manifest, profile = _contracts()
    graph = build_m1_m7_graph(workflow_manifest=manifest, runtime_profile=profile, activity_source_sha256=SOURCE)
    operation = {
        "task_id": "SCRUM-841", "repository": REPOSITORY,
        "run_id": "g1-841-test-run", "operation_id": "op-841-007",
        "activity_id": "tick-841-007", "base_sha": BASE, "head_sha": BASE,
        "working_branch": BRANCH, "scope_hash": SCOPE,
        "runtime_plan_digest": PLAN,
        "protocol_version": "dw.taskcontroller.continuation/v1",
        "continuation_ref": "sha256:" + "d" * 64,
        "cursor": {"controller_seq": 17, "executor_seq": 16},
    }
    action = {"action": "modify_approved_files", "idempotency_key": "op-841-007:M5:write-1", "payload_digest": "sha256:" + "e" * 64, "target_ref": "core/node-architect/scrum841-m1-m7-agent-workflow-r1.json"}
    authority = _activation_receipt(operation, action)
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
    assert result["authority_granted"] is False


def test_m7_holds_without_qualified_loop_host_and_sanitizes_checkpoint():
    manifest, profile = _contracts()
    graph = build_m1_m7_graph(workflow_manifest=manifest, runtime_profile=profile, activity_source_sha256=SOURCE)
    operation = {
        "task_id": "SCRUM-841", "repository": REPOSITORY,
        "run_id": "g1-841-test-run", "operation_id": "op-841-008",
        "activity_id": "tick-841-008", "base_sha": BASE, "head_sha": BASE,
        "working_branch": BRANCH, "scope_hash": SCOPE,
        "runtime_plan_digest": PLAN,
        "protocol_version": "dw.taskcontroller.continuation/v1",
        "continuation_ref": "sha256:" + "d" * 64,
        "cursor": {"controller_seq": 18, "executor_seq": 17},
    }
    action = {"action": "modify_approved_files", "idempotency_key": "op-841-008:M5:write-1", "payload_digest": "sha256:" + "e" * 64, "target_ref": "core/node-architect/scrum841-m1-m7-agent-workflow-r1.json"}
    authority = _activation_receipt(operation, action)
    host_request = {**action, "task_id": "SCRUM-841", "repository": REPOSITORY, "run_id": operation["run_id"], "operation_id": operation["operation_id"], "activity_id": operation["activity_id"], "base_sha": BASE, "head_sha": BASE, "working_branch": BRANCH, "scope_hash": SCOPE, "runtime_plan_digest": PLAN}
    host_receipt = {**host_request, "status": "VERIFIED", "readback_status": "VERIFIED", "readback_target": action["target_ref"], "readback_digest": "sha256:" + "2" * 64, "validation_outcome": "PASS", "validation_digest": "sha256:" + "3" * 64}
    result = graph.invoke({
        "operation_envelope": operation,
        "inputs": {
            "observer_qualified": True,
            "observer_receipt": {**operation, "classification": "CLEAR"},
            "action_request": action,
            "g2_activation_receipt": authority,
            "prior_host_action_requests": [host_request],
            "host_action_receipt": host_receipt,
            "checkpoint_state": {"current_activity": "M7", "browser_url": "https://invalid", "dom_refs": ["node-1"], "same": "same:4", "secret": "redacted"},
        },
        "host_action_requests": [], "settlement_requests": [],
    })
    assert result["status"] == "HOLD"
    assert result["reason_code"] == "M7_SETTLEMENT_HOST_UNQUALIFIED"
    assert result["settlement_requests"] == []
    assert result["executed_effects"] == []
    checkpoint = result["checkpoint_projection"]
    assert checkpoint["operation_id"] == operation["operation_id"]
    assert not ({"browser_url", "dom_refs", "same", "secret"} & set(checkpoint))
    assert result["authority_granted"] is False


def test_m7_emits_data_only_settlement_request_for_qualified_host():
    manifest, profile = _contracts()
    graph = build_m1_m7_graph(workflow_manifest=manifest, runtime_profile=profile, activity_source_sha256=SOURCE)
    operation = {
        "task_id": "SCRUM-841", "repository": REPOSITORY,
        "run_id": "g1-841-test-run", "operation_id": "op-841-009",
        "activity_id": "tick-841-009", "base_sha": BASE, "head_sha": BASE,
        "working_branch": BRANCH, "scope_hash": SCOPE,
        "runtime_plan_digest": PLAN,
        "protocol_version": "dw.taskcontroller.continuation/v1",
        "continuation_ref": "sha256:" + "d" * 64,
        "cursor": {"controller_seq": 19, "executor_seq": 18},
    }
    action = {"action": "modify_approved_files", "idempotency_key": "op-841-009:M5:write-1", "payload_digest": "sha256:" + "e" * 64, "target_ref": "core/node-architect/scrum841-m1-m7-agent-workflow-r1.json"}
    authority = _activation_receipt(operation, action)
    host_request = {**action, "task_id": "SCRUM-841", "repository": REPOSITORY, "run_id": operation["run_id"], "operation_id": operation["operation_id"], "activity_id": operation["activity_id"], "base_sha": BASE, "head_sha": BASE, "working_branch": BRANCH, "scope_hash": SCOPE, "runtime_plan_digest": PLAN}
    host_receipt = {**host_request, "status": "VERIFIED", "readback_status": "VERIFIED", "readback_target": action["target_ref"], "readback_digest": "sha256:" + "2" * 64, "validation_outcome": "PASS", "validation_digest": "sha256:" + "3" * 64}
    capability = {**operation, "artifact_type": "native-loop-capability-receipt", "qualified": True, "native_loop_owner": "hermes_host", "settlement_allowed": True, "receipt_digest": "sha256:" + "4" * 64}
    mailbox_capability = {**operation, "artifact_type": "m7-mailbox-notification-capability-receipt", "qualified": True, "single_executor_mailbox": True, "mailbox_patch_allowed": True, "controller_notification_allowed": True, "executor_mailbox_ref": "taskcontroller://executor/current", "controller_notification_target": "controller://bound", "receipt_digest": "sha256:" + "5" * 64}
    result = graph.invoke({
        "operation_envelope": operation,
        "inputs": {"observer_qualified": True, "observer_receipt": {**operation, "classification": "CLEAR"}, "action_request": action, "g2_activation_receipt": authority, "prior_host_action_requests": [host_request], "host_action_receipt": host_receipt, "settlement_capability_receipt": capability, "mailbox_notification_capability": mailbox_capability, "gate_readout": {"G1": "PASSED", "G2": "ACTIVE"}},
        "host_action_requests": [], "settlement_requests": [],
    })
    assert result["status"] == "WAIT"
    assert result["reason_code"] == "M7_SETTLEMENT_REQUESTED"
    assert len(result["host_action_requests"]) == 1
    mailbox_request = result["host_action_requests"][0]
    assert mailbox_request["action"] == "m7_executor_mailbox_patch_readback_controller_notify"
    assert mailbox_request["effect_performed"] is False
    assert len(result["settlement_requests"]) == 1
    request = result["settlement_requests"][0]
    assert request["requested_settlement"] == "complete"
    assert request["requires_host_readback"] is True
    assert request["settled"] is False
    assert request["authority_granted"] is False
    assert result["executed_effects"] == []
    assert result["authority_granted"] is False
    assert "complete_tick" not in result
    assert result["checkpoint_projection"]["gate_readout"] == {"G1": "PASSED", "G2": "ACTIVE"}



