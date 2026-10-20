"""Optional, data-only LangGraph workflow for the SCRUM-841 M1–M7 contract.

The graph validates host-owned identity and orchestrates activity results. It
never performs external I/O, invokes a capability, polls a mailbox, or settles a
native Loop tick. Evidence and checkpoint persistence remain host-owned.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import fnmatch
import json
from pathlib import Path
from typing import Any, TypedDict

from jsonschema import Draft202012Validator
from langgraph.graph import END, START, StateGraph

M1_M7_SOURCE_SHA256 = "sha256:6fa893e8224f824e562945cca8b7d66d382d060b1308bd0dbd481fdd612fa9c3"
ACTIVITY_IDS = ("M1", "M2", "M3", "M4", "M5", "M6", "M7")
EXPECTED_EDGES = tuple(zip(ACTIVITY_IDS, ACTIVITY_IDS[1:]))
_SHA40 = set("0123456789abcdef")


class WorkflowContractError(ValueError):
    """A source-bound SCRUM-841 workflow/profile contract is invalid."""


class WorkflowState(TypedDict, total=False):
    operation_envelope: dict[str, Any]
    checkpoint_projection: dict[str, Any]
    inputs: dict[str, Any]
    status: str
    reason_code: str
    current_activity: str
    activity_results: dict[str, Any]
    host_action_requests: list[dict[str, Any]]
    settlement_requests: list[dict[str, Any]]
    checkpoint_projection: dict[str, Any]
    child_dispatch_requests: list[dict[str, Any]]
    controller_exchange_requests: list[dict[str, Any]]
    host_action_receipt: dict[str, Any]
    verified_host_receipt: dict[str, Any]
    observer_receipt: dict[str, Any]
    mailbox_classification: str
    authority_granted: bool
    executed_effects: list[dict[str, Any]]


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise WorkflowContractError(reason)


def _valid_sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 40 and set(value) <= _SHA40


def _validate_contracts(
    workflow_manifest: Mapping[str, Any],
    runtime_profile: Mapping[str, Any],
    activity_source_sha256: str,
) -> None:
    _require(workflow_manifest.get("schema_version") == "1.0", "WORKFLOW_SCHEMA_VERSION_INVALID")
    _require(workflow_manifest.get("artifact_type") == "scrum841-m1-m7-workflow", "WORKFLOW_ARTIFACT_TYPE_INVALID")
    _require(workflow_manifest.get("workflow_id") == "scrum841-m1-m7-agent-workflow-r1", "WORKFLOW_ID_INVALID")
    _require(workflow_manifest.get("task_id") == "SCRUM-841", "WORKFLOW_TASK_MISMATCH")
    _require(workflow_manifest.get("source_sha256") == M1_M7_SOURCE_SHA256, "WORKFLOW_ACTIVITY_SOURCE_MISMATCH")
    _require(activity_source_sha256 == M1_M7_SOURCE_SHA256, "WORKFLOW_ACTIVITY_SOURCE_MISMATCH")
    activities = workflow_manifest.get("allowed_activities")
    _require(isinstance(activities, list) and tuple(activities) == ACTIVITY_IDS, "WORKFLOW_ACTIVITY_SET_INVALID")
    edges = workflow_manifest.get("edges")
    _require(isinstance(edges, list), "WORKFLOW_EDGES_INVALID")
    normalized: list[tuple[str, str]] = []
    for edge in edges:
        _require(isinstance(edge, Mapping), "WORKFLOW_EDGE_INVALID")
        source, target = edge.get("from"), edge.get("to")
        _require(source in ACTIVITY_IDS and target in ACTIVITY_IDS, "UNKNOWN_ACTIVITY_EDGE")
        normalized.append((str(source), str(target)))
    _require(tuple(normalized) == EXPECTED_EDGES, "WORKFLOW_EDGE_SET_INVALID")

    _require(runtime_profile.get("schema_version") == "1.0", "PROFILE_SCHEMA_VERSION_INVALID")
    _require(runtime_profile.get("artifact_type") == "scrum841-m1-m7-runtime-profile", "PROFILE_ARTIFACT_TYPE_INVALID")
    _require(runtime_profile.get("task_id") == workflow_manifest.get("task_id"), "PROFILE_TASK_MISMATCH")
    _require(runtime_profile.get("workflow_id") == workflow_manifest.get("workflow_id"), "PROFILE_WORKFLOW_MISMATCH")
    _require(runtime_profile.get("activity_source_sha256") == M1_M7_SOURCE_SHA256, "PROFILE_ACTIVITY_SOURCE_MISMATCH")
    _require(runtime_profile.get("runtime_plan_digest") == workflow_manifest.get("runtime_plan_digest"), "PROFILE_PLAN_MISMATCH")
    _require(runtime_profile.get("repository") == "nhatnguyenquang1838-coder/gwc", "PROFILE_REPOSITORY_MISMATCH")
    _require(_valid_sha(runtime_profile.get("base_sha")), "PROFILE_BASE_SHA_INVALID")
    _require(_valid_sha(runtime_profile.get("target_sha")), "PROFILE_TARGET_SHA_INVALID")
    _require(isinstance(runtime_profile.get("working_branch"), str) and runtime_profile["working_branch"].startswith("hermes/"), "PROFILE_BRANCH_INVALID")
    _require(isinstance(runtime_profile.get("scope_hash"), str) and runtime_profile["scope_hash"].startswith("sha256:") and len(runtime_profile["scope_hash"]) == 71, "PROFILE_SCOPE_HASH_INVALID")
    _require(runtime_profile.get("q0_authority_reused") is False, "Q0_AUTHORITY_REUSE_FORBIDDEN")
    _require(runtime_profile.get("native_loop_owner") == "hermes_host", "NATIVE_LOOP_OWNER_INVALID")


def _validate_operation_binding(state: WorkflowState, profile: Mapping[str, Any]) -> WorkflowState:
    operation = state.get("operation_envelope")
    if not isinstance(operation, Mapping):
        return {"status": "BLOCKED", "reason_code": "OPERATION_ENVELOPE_MISSING", "current_activity": "M1", "authority_granted": False, "executed_effects": []}
    required = ("task_id", "repository", "run_id", "operation_id", "activity_id", "base_sha", "head_sha", "working_branch", "scope_hash", "runtime_plan_digest")
    if any(not isinstance(operation.get(name), str) or not operation.get(name) for name in required):
        return {"status": "BLOCKED", "reason_code": "OPERATION_IDENTITY_MISSING", "current_activity": "M1", "authority_granted": False, "executed_effects": []}
    expected = {
        "task_id": profile["task_id"],
        "repository": profile["repository"],
        "base_sha": profile["base_sha"],
        "working_branch": profile["working_branch"],
        "scope_hash": profile["scope_hash"],
        "runtime_plan_digest": profile["runtime_plan_digest"],
    }
    if "run_id" in profile:
        expected["run_id"] = profile["run_id"]
    if any(operation.get(key) != value for key, value in expected.items()):
        return {"status": "BLOCKED", "reason_code": "OPERATION_BINDING_MISMATCH", "current_activity": "M1", "authority_granted": False, "executed_effects": []}
    if operation.get("head_sha") != operation.get("base_sha"):
        return {"status": "BLOCKED", "reason_code": "INITIAL_HEAD_BINDING_MISMATCH", "current_activity": "M1", "authority_granted": False, "executed_effects": []}
    checkpoint = state.get("checkpoint_projection")
    if checkpoint is not None:
        if not isinstance(checkpoint, Mapping):
            return {"status": "BLOCKED", "reason_code": "CHECKPOINT_PROJECTION_INVALID", "current_activity": "M1", "authority_granted": False, "executed_effects": []}
        forbidden = {"browser_url", "browser_session", "dom_refs", "screenshots", "composer_contents", "send_control_state", "same", "secret", "secrets"}
        forbidden_prefixes = ("same", "secret")
        if any(
            key in forbidden
            or any(key.lower().startswith(prefix) for prefix in forbidden_prefixes)
            for key in checkpoint
        ):
            return {"status": "BLOCKED", "reason_code": "CHECKPOINT_FORBIDDEN_BINDING", "current_activity": "M1", "authority_granted": False, "executed_effects": []}
        if any(checkpoint.get(key) != operation.get(key) for key in ("task_id", "repository", "run_id", "operation_id", "activity_id", "base_sha", "head_sha", "working_branch", "scope_hash", "runtime_plan_digest")):
            return {"status": "BLOCKED", "reason_code": "CHECKPOINT_BINDING_DRIFT", "current_activity": "M1", "authority_granted": False, "executed_effects": []}
        if checkpoint.get("current_activity") not in ACTIVITY_IDS:
            return {"status": "BLOCKED", "reason_code": "CHECKPOINT_ACTIVITY_INVALID", "current_activity": "M1", "authority_granted": False, "executed_effects": []}
    return {"status": "READY", "current_activity": "M1", "authority_granted": False, "executed_effects": []}


def _m1_observe(state: WorkflowState) -> WorkflowState:
    """M1 accepts only a qualified exact-ref receipt; it never polls."""
    inputs = state.get("inputs")
    inputs = inputs if isinstance(inputs, Mapping) else {}
    receipt = inputs.get("observer_receipt")
    if inputs.get("observer_qualified") is not True or not isinstance(receipt, Mapping):
        return {
            "status": "HOLD",
            "reason_code": "OBSERVER_UNQUALIFIED",
            "current_activity": "M1",
            "host_action_requests": [],
            "settlement_requests": [],
            "authority_granted": False,
            "executed_effects": [],
            "activity_results": {**dict(state.get("activity_results") or {}), "M1": {"status": "HOLD", "reason_code": "OBSERVER_UNQUALIFIED"}},
        }
    classification = receipt.get("classification")
    if classification not in {"CLEAR", "PENDING", "WAIT", "CONFLICT", "BLOCKED"}:
        return {
            "status": "HOLD",
            "reason_code": "OBSERVER_RECEIPT_INVALID",
            "current_activity": "M1",
            "host_action_requests": [],
            "settlement_requests": [],
            "authority_granted": False,
            "executed_effects": [],
            "activity_results": {**dict(state.get("activity_results") or {}), "M1": {"status": "HOLD", "reason_code": "OBSERVER_RECEIPT_INVALID"}},
        }
    if classification == "BLOCKED":
        return {
            "status": "HOLD",
            "reason_code": "M1_MAILBOX_BLOCKED",
            "current_activity": "M1",
            "host_action_requests": [],
            "settlement_requests": [],
            "authority_granted": False,
            "executed_effects": [],
            "activity_results": {**dict(state.get("activity_results") or {}), "M1": {"status": "BLOCKED", "reason_code": "M1_MAILBOX_BLOCKED"}},
        }
    return {
        "status": "CONTINUE",
        "reason_code": "M1_OBSERVATION_ACCEPTED",
        "current_activity": "M1",
        "mailbox_classification": classification,
        "observer_receipt": dict(receipt),
        "host_action_requests": list(state.get("host_action_requests") or []),
        "settlement_requests": list(state.get("settlement_requests") or []),
        "authority_granted": False,
        "executed_effects": [],
        "activity_results": {**dict(state.get("activity_results") or {}), "M1": {"status": classification, "receipt_digest": receipt.get("receipt_digest")}},
    }


def _m2_validate(state: WorkflowState) -> WorkflowState:
    """M2 validates source, protocol, cursor, continuation, identity and deadlock."""
    operation = state.get("operation_envelope")
    receipt = state.get("observer_receipt")
    if not isinstance(operation, Mapping) or not isinstance(receipt, Mapping):
        return {"status": "HOLD", "reason_code": "M2_OBSERVATION_MISSING", "current_activity": "M2", "authority_granted": False, "executed_effects": []}
    identity_fields = ("task_id", "repository", "run_id", "operation_id", "activity_id", "base_sha", "head_sha", "working_branch", "scope_hash", "runtime_plan_digest")
    if any(receipt.get(field) != operation.get(field) for field in identity_fields):
        return {"status": "HOLD", "reason_code": "M2_BINDING_MISMATCH", "current_activity": "M2", "authority_granted": False, "executed_effects": []}
    if operation.get("protocol_version") != "dw.taskcontroller.continuation/v1" or receipt.get("protocol_version") != operation.get("protocol_version"):
        return {"status": "HOLD", "reason_code": "M2_PROTOCOL_MISMATCH", "current_activity": "M2", "authority_granted": False, "executed_effects": []}
    continuation = operation.get("continuation_ref")
    if not isinstance(continuation, str) or not continuation.startswith("sha256:") or len(continuation) != 71 or receipt.get("continuation_ref") != continuation:
        return {"status": "HOLD", "reason_code": "M2_CONTINUATION_MISMATCH", "current_activity": "M2", "authority_granted": False, "executed_effects": []}
    expected_cursor = operation.get("cursor")
    observed_cursor = receipt.get("cursor")
    if not isinstance(expected_cursor, Mapping) or not isinstance(observed_cursor, Mapping):
        return {"status": "HOLD", "reason_code": "M2_CURSOR_MISSING", "current_activity": "M2", "authority_granted": False, "executed_effects": []}
    cursor_keys = ("controller_seq", "executor_seq")
    if any(not isinstance(expected_cursor.get(key), int) or expected_cursor.get(key) < 0 or observed_cursor.get(key) != expected_cursor.get(key) for key in cursor_keys):
        return {"status": "HOLD", "reason_code": "M2_CURSOR_MISMATCH", "current_activity": "M2", "authority_granted": False, "executed_effects": []}
    if receipt.get("deadlock_detected") is True:
        return {"status": "HOLD", "reason_code": "DEADLOCK_DETECTED", "current_activity": "M2", "authority_granted": False, "executed_effects": []}
    return {
        "status": "CONTINUE",
        "reason_code": "M2_PROTOCOL_AND_BINDINGS_VALID",
        "current_activity": "M2",
        "host_action_requests": list(state.get("host_action_requests") or []),
        "settlement_requests": list(state.get("settlement_requests") or []),
        "authority_granted": False,
        "executed_effects": [],
        "activity_results": {**dict(state.get("activity_results") or {}), "M2": {"status": "PASS", "cursor": dict(observed_cursor), "continuation_ref": continuation}},
    }


def _m3_review(state: WorkflowState) -> WorkflowState:
    """M3 consumes a typed read-only Red Team receipt; it never dispatches."""
    operation = state.get("operation_envelope")
    inputs = state.get("inputs")
    input_map = inputs if isinstance(inputs, Mapping) else {}
    receipt = input_map.get("red_team_receipt")
    prior = dict(state.get("activity_results") or {})
    classification = state.get("mailbox_classification")
    if classification not in {"PENDING", "WAIT"}:
        return {
            "status": "CONTINUE",
            "reason_code": "M3_NOT_REQUIRED",
            "current_activity": "M3",
            "child_dispatch_requests": [],
            "activity_results": {**prior, "M3": {"status": "NOT_APPLICABLE", "analyzer_disposition": "ANALYZER_NOT_DECLARED"}},
            "authority_granted": False,
            "executed_effects": [],
        }
    if not isinstance(operation, Mapping) or not isinstance(receipt, Mapping):
        return {"status": "HOLD", "reason_code": "M3_RED_TEAM_RECEIPT_MISSING", "current_activity": "M3", "child_dispatch_requests": [], "authority_granted": False, "executed_effects": []}
    identity_fields = ("task_id", "repository", "run_id", "operation_id", "activity_id", "base_sha", "head_sha", "working_branch", "scope_hash", "runtime_plan_digest", "protocol_version", "continuation_ref", "cursor")
    if any(receipt.get(field) != operation.get(field) for field in identity_fields):
        return {"status": "HOLD", "reason_code": "M3_RED_TEAM_BINDING_MISMATCH", "current_activity": "M3", "child_dispatch_requests": [], "authority_granted": False, "executed_effects": []}
    digest = receipt.get("result_digest")
    if receipt.get("status") != "VERIFIED" or receipt.get("read_only") is not True or not isinstance(digest, str) or not digest.startswith("sha256:") or len(digest) != 71:
        return {"status": "HOLD", "reason_code": "M3_RED_TEAM_RECEIPT_INVALID", "current_activity": "M3", "child_dispatch_requests": [], "authority_granted": False, "executed_effects": []}
    child_contract = input_map.get("typed_read_only_child_contract")
    capacity = input_map.get("max_children", 0)
    analyzer = "ANALYZER_NOT_DECLARED"
    if isinstance(child_contract, Mapping) and isinstance(capacity, int) and capacity > 0:
        # This SCRUM-841 plan has max_children=0. A child contract is only
        # evidence; this graph never dispatches a reviewer or agent.
        analyzer = "ANALYZER_CAPACITY_NOT_AUTHORIZED"
    return {
        "status": "CONTINUE",
        "reason_code": "M3_READ_ONLY_REVIEW_VALIDATED",
        "current_activity": "M3",
        "child_dispatch_requests": [],
        "activity_results": {**prior, "M3": {"status": "PASS", "red_team_receipt_digest": digest, "analyzer_disposition": analyzer}},
        "authority_granted": False,
        "executed_effects": [],
    }


def _m4_reconcile(state: WorkflowState) -> WorkflowState:
    """M4 emits at most one bound reconciliation request; it never sends it."""
    inputs = state.get("inputs")
    input_map = inputs if isinstance(inputs, Mapping) else {}
    classification = state.get("mailbox_classification")
    conflict = classification == "CONFLICT" or input_map.get("controller_blocker") is True or input_map.get("review_conflict") is True
    prior = dict(state.get("activity_results") or {})
    if not conflict:
        return {"status": "CONTINUE", "reason_code": "M4_NO_CONFLICT", "current_activity": "M4", "controller_exchange_requests": [], "activity_results": {**prior, "M4": {"status": "NOT_APPLICABLE"}}, "authority_granted": False, "executed_effects": []}
    operation = state.get("operation_envelope")
    binding = input_map.get("controller_exchange_binding")
    if not isinstance(operation, Mapping) or not isinstance(binding, Mapping):
        return {"status": "HOLD", "reason_code": "M4_BOUND_EXCHANGE_MISSING", "current_activity": "M4", "controller_exchange_requests": [], "authority_granted": False, "executed_effects": []}
    blocker_key = binding.get("blocker_key")
    if not isinstance(blocker_key, str) or not blocker_key.strip():
        return {"status": "HOLD", "reason_code": "M4_BLOCKER_KEY_MISSING", "current_activity": "M4", "controller_exchange_requests": [], "authority_granted": False, "executed_effects": []}
    identity_fields = ("task_id", "repository", "run_id", "operation_id", "activity_id", "base_sha", "head_sha", "working_branch", "scope_hash", "runtime_plan_digest", "protocol_version", "continuation_ref", "cursor")
    if any(binding.get(field) != operation.get(field) for field in identity_fields):
        return {"status": "HOLD", "reason_code": "M4_BOUND_EXCHANGE_IDENTITY_MISMATCH", "current_activity": "M4", "controller_exchange_requests": [], "authority_granted": False, "executed_effects": []}
    idempotency_key = f"{operation['operation_id']}:M4:{blocker_key}"
    prior_requests = input_map.get("prior_controller_exchange_requests", state.get("controller_exchange_requests", []))
    if not isinstance(prior_requests, list):
        return {"status": "HOLD", "reason_code": "M4_PRIOR_REQUEST_LEDGER_INVALID", "current_activity": "M4", "controller_exchange_requests": [], "authority_granted": False, "executed_effects": []}
    if any(isinstance(item, Mapping) and item.get("idempotency_key") == idempotency_key for item in prior_requests):
        return {"status": "WAIT", "reason_code": "M4_RECONCILIATION_ALREADY_REQUESTED", "current_activity": "M4", "controller_exchange_requests": [], "authority_granted": False, "executed_effects": []}
    request = {
        "request_type": "controller_exchange",
        **{field: operation[field] for field in identity_fields},
        "blocker_key": blocker_key,
        "idempotency_key": idempotency_key,
        "authority_granted": False,
        "effect_performed": False,
    }
    return {
        "status": "WAIT",
        "reason_code": "M4_CONTROLLER_EXCHANGE_REQUESTED",
        "current_activity": "M4",
        "controller_exchange_requests": [request],
        "activity_results": {**prior, "M4": {"status": "WAIT", "idempotency_key": idempotency_key}},
        "authority_granted": False,
        "executed_effects": [],
    }


def _m5_request_host_action(state: WorkflowState, profile: Mapping[str, Any]) -> WorkflowState:
    """M5 emits one source-bound request; only the external host may act."""
    inputs = state.get("inputs")
    input_map = inputs if isinstance(inputs, Mapping) else {}
    if input_map.get("prior_effect_outcome_unknown") is True:
        return {"status": "HOLD", "reason_code": "M5_UNKNOWN_EFFECT_REQUIRES_RECONCILIATION", "current_activity": "M5", "host_action_requests": [], "executed_effects": [], "authority_granted": False}
    operation = state.get("operation_envelope")
    action = input_map.get("action_request")
    activation = input_map.get("g2_activation_receipt")
    if not isinstance(operation, Mapping) or not isinstance(action, Mapping) or not isinstance(activation, Mapping):
        return {"status": "HOLD", "reason_code": "M5_TYPED_ACTION_OR_AUTHORITY_MISSING", "current_activity": "M5", "host_action_requests": [], "executed_effects": [], "authority_granted": False}
    action_id = action.get("action")
    idempotency_key = action.get("idempotency_key")
    payload_digest = action.get("payload_digest")
    target = action.get("target_ref")
    if not isinstance(action_id, str) or not action_id or not isinstance(idempotency_key, str) or not idempotency_key or not isinstance(payload_digest, str) or not isinstance(target, str) or not target:
        return {"status": "HOLD", "reason_code": "M5_ACTION_REQUEST_INVALID", "current_activity": "M5", "host_action_requests": [], "executed_effects": [], "authority_granted": False}
    if not idempotency_key.startswith(f"{operation.get('operation_id')}:M5:"):
        return {"status": "HOLD", "reason_code": "M5_IDEMPOTENCY_BINDING_MISMATCH", "current_activity": "M5", "host_action_requests": [], "executed_effects": [], "authority_granted": False}
    if not payload_digest.startswith("sha256:") or len(payload_digest) != 71:
        return {"status": "HOLD", "reason_code": "M5_ACTION_REQUEST_INVALID", "current_activity": "M5", "host_action_requests": [], "executed_effects": [], "authority_granted": False}
    expiry = activation.get("expires_at")
    try:
        parsed_expiry = datetime.fromisoformat(str(expiry).replace("Z", "+00:00"))
    except ValueError:
        parsed_expiry = None
    if (
        activation.get("artifact_type") != "g2-activation-receipt"
        or activation.get("activation_state") != "ACTIVE"
        or activation.get("execution_started") is not False
        or parsed_expiry is None
        or parsed_expiry.tzinfo is None
        or parsed_expiry.utcoffset() is None
        or parsed_expiry <= datetime.now(timezone.utc)
    ):
        return {"status": "HOLD", "reason_code": "M5_G2_ACTIVATION_RECEIPT_INVALID", "current_activity": "M5", "host_action_requests": [], "executed_effects": [], "authority_granted": False}
    approval = activation.get("approval_validation")
    if not isinstance(approval, Mapping):
        return {"status": "HOLD", "reason_code": "M5_APPROVAL_VALIDATION_MISSING", "current_activity": "M5", "host_action_requests": [], "executed_effects": [], "authority_granted": False}
    approval_expected = {
        "task_id": operation.get("task_id"), "repository": operation.get("repository"),
        "base_sha": operation.get("base_sha"), "head_sha": operation.get("head_sha"),
        "working_branch": operation.get("working_branch"), "scope_hash": operation.get("scope_hash"),
        "risk_class": activation.get("risk_class"),
        "authorized_actions": list(activation.get("authorized_actions") or []),
    }
    if (
        approval.get("outcome") != "VALID"
        or approval.get("approval_valid") is not True
        or activation.get("approval_request_id") != approval.get("approval_request_ref")
        or activation.get("approval_validation_digest") != approval.get("validation_digest")
        or any(approval.get(key) != value for key, value in approval_expected.items())
        or activation.get("validated_actor_id") != activation.get("approval_request_actor_id")
        or any(approval.get(flag) is not False for flag in ("execution_authority_granted", "merge_authority_granted", "deployment_authority_granted", "production_authority_granted"))
    ):
        return {"status": "HOLD", "reason_code": "M5_APPROVAL_VALIDATION_BINDING_MISMATCH", "current_activity": "M5", "host_action_requests": [], "executed_effects": [], "authority_granted": False}
    expected = {
        "task_id": operation.get("task_id"), "repository": operation.get("repository"),
        "run_id": operation.get("run_id"), "branch": operation.get("working_branch"),
        "base_sha": operation.get("base_sha"), "head_sha": operation.get("head_sha"),
        "scope_hash": operation.get("scope_hash"), "gate": "G2_EXECUTION",
    }
    if any(activation.get(field) != value for field, value in expected.items()):
        return {"status": "HOLD", "reason_code": "M5_AUTHORITY_BINDING_MISMATCH", "current_activity": "M5", "host_action_requests": [], "executed_effects": [], "authority_granted": False}
    profile_actions = profile.get("authorized_actions", [])
    profile_paths = profile.get("authorized_paths", [])
    if action_id not in (activation.get("authorized_actions") or []) or action_id not in profile_actions or target not in (activation.get("authorized_paths") or []) or not any(isinstance(path, str) and fnmatch.fnmatchcase(target, path) for path in profile_paths):
        return {"status": "HOLD", "reason_code": "M5_ACTION_OUTSIDE_AUTHORIZED_SCOPE", "current_activity": "M5", "host_action_requests": [], "executed_effects": [], "authority_granted": False}
    if not str(activation.get("approval_request_id") or "") or not str(activation.get("approval_validation_digest") or "").startswith("sha256:") or not str(activation.get("envelope_digest") or "").startswith("sha256:"):
        return {"status": "HOLD", "reason_code": "M5_AUTHORITY_PROVENANCE_MISSING", "current_activity": "M5", "host_action_requests": [], "executed_effects": [], "authority_granted": False}
    prior_requests = input_map.get("prior_host_action_requests", state.get("host_action_requests", []))
    if not isinstance(prior_requests, list):
        return {"status": "HOLD", "reason_code": "M5_PRIOR_REQUEST_LEDGER_INVALID", "current_activity": "M5", "host_action_requests": [], "executed_effects": [], "authority_granted": False}
    host_receipt = input_map.get("host_action_receipt")
    if isinstance(host_receipt, Mapping):
        prior_match = any(isinstance(item, Mapping) and item.get("idempotency_key") == idempotency_key for item in prior_requests)
        if not prior_match or host_receipt.get("idempotency_key") != idempotency_key:
            return {"status": "HOLD", "reason_code": "M5_HOST_RECEIPT_WITHOUT_REQUEST", "current_activity": "M5", "host_action_requests": [], "executed_effects": [], "authority_granted": False}
        return {"status": "CONTINUE", "reason_code": "M5_HOST_RECEIPT_AVAILABLE", "current_activity": "M5", "host_action_requests": [], "host_action_receipt": dict(host_receipt), "executed_effects": [], "authority_granted": False}
    if any(isinstance(item, Mapping) and item.get("idempotency_key") == idempotency_key for item in prior_requests):
        return {"status": "WAIT", "reason_code": "M5_ACTION_ALREADY_REQUESTED", "current_activity": "M5", "host_action_requests": [], "executed_effects": [], "authority_granted": False}
    request = {
        "request_type": "host_action_request",
        "task_id": operation["task_id"], "repository": operation["repository"],
        "run_id": operation["run_id"], "operation_id": operation["operation_id"],
        "activity_id": operation["activity_id"], "base_sha": operation["base_sha"],
        "head_sha": operation["head_sha"], "working_branch": operation["working_branch"],
        "scope_hash": operation["scope_hash"], "runtime_plan_digest": operation["runtime_plan_digest"],
        "action": action_id, "target_ref": target, "payload_digest": payload_digest,
        "idempotency_key": idempotency_key, "authority_ref": activation["envelope_digest"],
        "approval_request_id": activation["approval_request_id"],
        "approval_validation_digest": activation["approval_validation_digest"],
        "effect_performed": False, "authority_granted": False,
    }
    return {"status": "WAIT", "reason_code": "M5_HOST_ACTION_REQUESTED", "current_activity": "M5", "host_action_requests": [request], "executed_effects": [], "authority_granted": False}


def _m6_verify_host_receipt(state: WorkflowState) -> WorkflowState:
    """M6 verifies the exact host receipt, validator and target readback."""
    operation = state.get("operation_envelope")
    inputs = state.get("inputs")
    input_map = inputs if isinstance(inputs, Mapping) else {}
    receipt = state.get("host_action_receipt") or input_map.get("host_action_receipt")
    action = input_map.get("action_request")
    if not isinstance(operation, Mapping) or not isinstance(receipt, Mapping) or not isinstance(action, Mapping):
        return {"status": "HOLD", "reason_code": "M6_EXACT_HOST_RECEIPT_MISSING", "current_activity": "M6", "authority_granted": False, "executed_effects": []}
    exact_fields = ("task_id", "repository", "run_id", "operation_id", "activity_id", "base_sha", "head_sha", "working_branch", "scope_hash", "runtime_plan_digest")
    if any(receipt.get(field) != operation.get(field) for field in exact_fields):
        return {"status": "HOLD", "reason_code": "M6_HOST_RECEIPT_BINDING_MISMATCH", "current_activity": "M6", "authority_granted": False, "executed_effects": []}
    for field in ("action", "target_ref", "payload_digest", "idempotency_key"):
        if receipt.get(field) != action.get(field):
            return {"status": "HOLD", "reason_code": "M6_HOST_ACTION_MISMATCH", "current_activity": "M6", "authority_granted": False, "executed_effects": []}
    readback_digest = receipt.get("readback_digest")
    validation_digest = receipt.get("validation_digest")
    if receipt.get("status") != "VERIFIED" or receipt.get("readback_status") != "VERIFIED" or receipt.get("readback_target") != action.get("target_ref"):
        return {"status": "HOLD", "reason_code": "M6_EXACT_READBACK_MISMATCH", "current_activity": "M6", "authority_granted": False, "executed_effects": []}
    if receipt.get("validation_outcome") != "PASS" or not isinstance(validation_digest, str) or not validation_digest.startswith("sha256:") or len(validation_digest) != 71:
        return {"status": "HOLD", "reason_code": "M6_VALIDATOR_EVIDENCE_INVALID", "current_activity": "M6", "authority_granted": False, "executed_effects": []}
    if not isinstance(readback_digest, str) or not readback_digest.startswith("sha256:") or len(readback_digest) != 71:
        return {"status": "HOLD", "reason_code": "M6_READBACK_DIGEST_INVALID", "current_activity": "M6", "authority_granted": False, "executed_effects": []}
    prior = dict(state.get("activity_results") or {})
    return {
        "status": "CONTINUE",
        "reason_code": "M6_EXACT_EVIDENCE_VERIFIED",
        "current_activity": "M6",
        "activity_results": {**prior, "M6": {"status": "PASS", "readback_digest": readback_digest, "validation_digest": validation_digest}},
        "verified_host_receipt": dict(receipt),
        "authority_granted": False,
        "executed_effects": [],
    }


def _m7_settlement_request(state: WorkflowState, profile: Mapping[str, Any]) -> WorkflowState:
    """M7 emits a host-owned settlement request; it never calls LoopManager."""
    operation = state.get("operation_envelope")
    inputs = state.get("inputs")
    input_map = inputs if isinstance(inputs, Mapping) else {}
    prior = dict(state.get("activity_results") or {})
    checkpoint = {
        key: value for key, value in {
            "task_id": operation.get("task_id") if isinstance(operation, Mapping) else None,
            "repository": operation.get("repository") if isinstance(operation, Mapping) else None,
            "run_id": operation.get("run_id") if isinstance(operation, Mapping) else None,
            "operation_id": operation.get("operation_id") if isinstance(operation, Mapping) else None,
            "activity_id": operation.get("activity_id") if isinstance(operation, Mapping) else None,
            "base_sha": operation.get("base_sha") if isinstance(operation, Mapping) else None,
            "head_sha": operation.get("head_sha") if isinstance(operation, Mapping) else None,
            "working_branch": operation.get("working_branch") if isinstance(operation, Mapping) else None,
            "scope_hash": operation.get("scope_hash") if isinstance(operation, Mapping) else None,
            "runtime_plan_digest": operation.get("runtime_plan_digest") if isinstance(operation, Mapping) else None,
            "protocol_version": operation.get("protocol_version") if isinstance(operation, Mapping) else None,
            "continuation_ref": operation.get("continuation_ref") if isinstance(operation, Mapping) else None,
            "cursor": operation.get("cursor") if isinstance(operation, Mapping) else None,
            "current_activity": "M7",
            "mailbox_classification": state.get("mailbox_classification"),
            "activity_results": prior,
            "receipt_refs": [value.get("readback_digest") for key, value in prior.items() if isinstance(value, Mapping) and value.get("readback_digest")],
            "idempotency_keys": [item.get("idempotency_key") for item in (state.get("host_action_requests") or []) if isinstance(item, Mapping) and item.get("idempotency_key")],
            "controller_exchange_idempotency_keys": [item.get("idempotency_key") for item in (state.get("controller_exchange_requests") or []) if isinstance(item, Mapping) and item.get("idempotency_key")],
            "settlement_idempotency_keys": [item.get("idempotency_key") for item in (state.get("settlement_requests") or []) if isinstance(item, Mapping) and item.get("idempotency_key")],
        }.items() if value is not None
    }
    gate_readout = input_map.get("gate_readout")
    allowed_gate_states = {"NOT_STARTED", "ACTIVE", "WAITING", "BLOCKED", "PASSED", "FAILED", "NOT_APPLICABLE"}
    if isinstance(gate_readout, Mapping):
        checkpoint["gate_readout"] = {key: gate_readout[key] for key in ("G1", "G2", "G3", "G4", "G5", "G6") if key in gate_readout and gate_readout[key] in allowed_gate_states}
    if prior.get("M6", {}).get("status") != "PASS":
        return {"status": "HOLD", "reason_code": "M7_M6_EVIDENCE_REQUIRED", "current_activity": "M7", "checkpoint_projection": checkpoint, "settlement_requests": [], "authority_granted": False, "executed_effects": []}
    capability = input_map.get("settlement_capability_receipt")
    if not isinstance(operation, Mapping) or not isinstance(capability, Mapping):
        return {"status": "HOLD", "reason_code": "M7_SETTLEMENT_HOST_UNQUALIFIED", "current_activity": "M7", "checkpoint_projection": checkpoint, "settlement_requests": [], "authority_granted": False, "executed_effects": []}
    fields = ("task_id", "repository", "run_id", "operation_id", "activity_id", "base_sha", "head_sha", "working_branch", "scope_hash", "runtime_plan_digest", "protocol_version", "continuation_ref", "cursor")
    if capability.get("artifact_type") != "native-loop-capability-receipt" or any(capability.get(key) != operation.get(key) for key in fields):
        return {"status": "HOLD", "reason_code": "M7_SETTLEMENT_CAPABILITY_BINDING_MISMATCH", "current_activity": "M7", "checkpoint_projection": checkpoint, "settlement_requests": [], "authority_granted": False, "executed_effects": []}
    if capability.get("qualified") is not True or capability.get("native_loop_owner") != "hermes_host" or capability.get("settlement_allowed") is not True:
        return {"status": "HOLD", "reason_code": "M7_SETTLEMENT_HOST_UNQUALIFIED", "current_activity": "M7", "checkpoint_projection": checkpoint, "settlement_requests": [], "authority_granted": False, "executed_effects": []}
    mailbox = input_map.get("mailbox_notification_capability")
    if not isinstance(mailbox, Mapping):
        return {"status": "HOLD", "reason_code": "M7_MAILBOX_CAPABILITY_UNQUALIFIED", "current_activity": "M7", "checkpoint_projection": checkpoint, "host_action_requests": [], "settlement_requests": [], "authority_granted": False, "executed_effects": []}
    if any(mailbox.get(key) != operation.get(key) for key in fields):
        return {"status": "HOLD", "reason_code": "M7_MAILBOX_CAPABILITY_BINDING_MISMATCH", "current_activity": "M7", "checkpoint_projection": checkpoint, "host_action_requests": [], "settlement_requests": [], "authority_granted": False, "executed_effects": []}
    mailbox_ref = mailbox.get("executor_mailbox_ref")
    controller_target = mailbox.get("controller_notification_target")
    mailbox_digest = mailbox.get("receipt_digest")
    if (
        mailbox.get("artifact_type") != "m7-mailbox-notification-capability-receipt"
        or mailbox.get("qualified") is not True
        or mailbox.get("single_executor_mailbox") is not True
        or mailbox.get("mailbox_patch_allowed") is not True
        or mailbox.get("controller_notification_allowed") is not True
        or not isinstance(mailbox_ref, str) or not mailbox_ref
        or not isinstance(controller_target, str) or not controller_target
        or not isinstance(mailbox_digest, str) or not mailbox_digest.startswith("sha256:") or len(mailbox_digest) != 71
    ):
        return {"status": "HOLD", "reason_code": "M7_MAILBOX_CAPABILITY_UNQUALIFIED", "current_activity": "M7", "checkpoint_projection": checkpoint, "host_action_requests": [], "settlement_requests": [], "authority_granted": False, "executed_effects": []}
    mailbox_key = f"{operation['operation_id']}:M7:mailbox-update-notify"
    prior_host_requests = input_map.get("prior_m7_mailbox_requests", state.get("host_action_requests", []))
    if not isinstance(prior_host_requests, list):
        return {"status": "HOLD", "reason_code": "M7_PRIOR_HOST_REQUEST_LEDGER_INVALID", "current_activity": "M7", "checkpoint_projection": checkpoint, "host_action_requests": [], "settlement_requests": [], "authority_granted": False, "executed_effects": []}
    already_sent = any(isinstance(item, Mapping) and item.get("idempotency_key") == mailbox_key for item in prior_host_requests)
    mailbox_readback = input_map.get("m7_mailbox_readback")
    if already_sent:
        if not isinstance(mailbox_readback, Mapping) or mailbox_readback.get("idempotency_key") != mailbox_key:
            return {"status": "WAIT", "reason_code": "M7_MAILBOX_READBACK_PENDING", "current_activity": "M7", "checkpoint_projection": checkpoint, "host_action_requests": [], "settlement_requests": [], "authority_granted": False, "executed_effects": []}
        if mailbox_readback.get("status") != "VERIFIED" or mailbox_readback.get("executor_mailbox_status") != "VERIFIED" or mailbox_readback.get("controller_notification_status") != "VERIFIED" or not isinstance(mailbox_readback.get("readback_digest"), str) or not mailbox_readback["readback_digest"].startswith("sha256:") or len(mailbox_readback["readback_digest"]) != 71:
            return {"status": "HOLD", "reason_code": "M7_MAILBOX_READBACK_INVALID", "current_activity": "M7", "checkpoint_projection": checkpoint, "host_action_requests": [], "settlement_requests": [], "authority_granted": False, "executed_effects": []}
        mailbox_requests: list[dict[str, Any]] = []
    else:
        mailbox_requests = [{
            "request_type": "host_action_request",
            "action": "m7_executor_mailbox_patch_readback_controller_notify",
            "task_id": operation["task_id"], "repository": operation["repository"],
            "run_id": operation["run_id"], "operation_id": operation["operation_id"],
            "activity_id": operation["activity_id"], "base_sha": operation["base_sha"],
            "head_sha": operation["head_sha"], "working_branch": operation["working_branch"],
            "scope_hash": operation["scope_hash"], "runtime_plan_digest": operation["runtime_plan_digest"],
            "executor_mailbox_ref": mailbox_ref, "controller_notification_target": controller_target,
            "idempotency_key": mailbox_key, "capability_ref": mailbox_digest,
            "effect_performed": False, "authority_granted": False,
        }]
    idempotency_key = f"{operation['operation_id']}:M7:settlement"
    prior_requests = input_map.get("prior_settlement_requests", state.get("settlement_requests", []))
    if not isinstance(prior_requests, list):
        return {"status": "HOLD", "reason_code": "M7_PRIOR_SETTLEMENT_LEDGER_INVALID", "current_activity": "M7", "checkpoint_projection": checkpoint, "settlement_requests": [], "authority_granted": False, "executed_effects": []}
    if any(isinstance(item, Mapping) and item.get("idempotency_key") == idempotency_key for item in prior_requests):
        return {"status": "WAIT", "reason_code": "M7_SETTLEMENT_ALREADY_REQUESTED", "current_activity": "M7", "checkpoint_projection": checkpoint, "settlement_requests": [], "authority_granted": False, "executed_effects": []}
    settlement = {
        "request_type": "native_loop_settlement_request",
        "task_id": operation["task_id"], "repository": operation["repository"],
        "run_id": operation["run_id"], "operation_id": operation["operation_id"],
        "activity_id": operation["activity_id"], "base_sha": operation["base_sha"],
        "head_sha": operation["head_sha"], "working_branch": operation["working_branch"],
        "scope_hash": operation["scope_hash"], "runtime_plan_digest": operation["runtime_plan_digest"],
        "requested_settlement": "complete", "idempotency_key": idempotency_key,
        "host_capability_ref": capability.get("receipt_digest"),
        "evidence_refs": list(checkpoint.get("receipt_refs", [])),
        "host_action_request_key": mailbox_key,
        "requires_host_readback": True,
        "mailbox_readback_digest": mailbox_readback.get("readback_digest") if isinstance(mailbox_readback, Mapping) else None,
        "authority_granted": False, "settled": False,
    }
    return {"status": "WAIT", "reason_code": "M7_SETTLEMENT_REQUESTED", "current_activity": "M7", "checkpoint_projection": checkpoint, "host_action_requests": mailbox_requests, "settlement_requests": [settlement], "authority_granted": False, "executed_effects": []}


def load_m1_m7_contracts(repository_root: Path | str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load and validate the explicit SCRUM-841 manifest/profile pair."""
    root = Path(repository_root).resolve()
    workflow_path = root / "core/node-architect/scrum841-m1-m7-agent-workflow-r1.json"
    profile_path = root / "core/node-architect/scrum841-m1-m7-runtime-profile-r1.json"
    workflow_schema_path = root / "schemas/node-architect/scrum841-m1-m7-agent-workflow.schema.json"
    profile_schema_path = root / "schemas/node-architect/scrum841-m1-m7-runtime-profile.schema.json"
    try:
        manifest = json.loads(workflow_path.read_text(encoding="utf-8"))
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        workflow_schema = json.loads(workflow_schema_path.read_text(encoding="utf-8"))
        profile_schema = json.loads(profile_schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowContractError("WORKFLOW_CONTRACT_SOURCE_UNAVAILABLE") from exc
    Draft202012Validator.check_schema(workflow_schema)
    Draft202012Validator.check_schema(profile_schema)
    workflow_errors = list(Draft202012Validator(workflow_schema).iter_errors(manifest))
    profile_errors = list(Draft202012Validator(profile_schema).iter_errors(profile))
    if workflow_errors or profile_errors:
        raise WorkflowContractError("WORKFLOW_CONTRACT_SCHEMA_INVALID")
    _validate_contracts(manifest, profile, str(manifest.get("source_sha256") or ""))
    if manifest.get("runtime_plan_digest") != profile.get("runtime_plan_digest"):
        raise WorkflowContractError("WORKFLOW_PROFILE_PLAN_BINDING_MISMATCH")
    if profile.get("target_ref") == profile.get("base_ref") or profile.get("target_sha") == profile.get("base_sha"):
        raise WorkflowContractError("WORKFLOW_INTEGRATION_TARGET_NOT_DISTINCT")
    if not profile.get("authorized_paths") or not profile.get("authorized_actions"):
        raise WorkflowContractError("WORKFLOW_AUTHORIZED_SCOPE_MISSING")
    return manifest, profile


def _start_activity(state: WorkflowState) -> str:
    if state.get("status") != "READY":
        return END
    checkpoint = state.get("checkpoint_projection")
    if isinstance(checkpoint, Mapping):
        activity = checkpoint.get("current_activity")
        return str(activity) if activity in ACTIVITY_IDS else END
    return "M1"


def build_m1_m7_graph(
    *,
    workflow_manifest: Mapping[str, Any],
    runtime_profile: Mapping[str, Any],
    activity_source_sha256: str,
    execution_binding: Mapping[str, Any] | None = None,
):
    """Compile the optional graph. Q0 rebinding is observation-only, never authority."""
    if not isinstance(workflow_manifest, Mapping) or not isinstance(runtime_profile, Mapping):
        raise WorkflowContractError("WORKFLOW_CONTRACT_INPUT_INVALID")
    _validate_contracts(workflow_manifest, runtime_profile, activity_source_sha256)
    if execution_binding is not None:
        _require(isinstance(execution_binding, Mapping), "EXECUTION_BINDING_INVALID")
        _require(execution_binding.get("task_id") == "SCRUM-781", "EXECUTION_TASK_INVALID")
        _require(str(execution_binding.get("run_id", "")).startswith("scrum781-q0-"), "EXECUTION_RUN_INVALID")
        _require(str(execution_binding.get("working_branch", "")).startswith("fix/SCRUM-781-q0-"), "EXECUTION_BRANCH_INVALID")
        _require(execution_binding.get("repository") == runtime_profile["repository"], "EXECUTION_REPOSITORY_INVALID")
        _require(_valid_sha(execution_binding.get("base_sha")), "EXECUTION_BASE_INVALID")
        for field in ("scope_hash", "runtime_plan_digest"):
            value = execution_binding.get(field)
            _require(isinstance(value, str) and value.startswith("sha256:") and len(value) == 71, "EXECUTION_DIGEST_INVALID")
        _require(execution_binding.get("authorized_actions") == [] and execution_binding.get("authorized_paths") == [], "EXECUTION_BINDING_MUST_BE_OBSERVATION_ONLY")
        runtime_profile = {**dict(runtime_profile), **{key: execution_binding[key] for key in ("task_id", "run_id", "repository", "base_sha", "working_branch", "scope_hash", "runtime_plan_digest", "authorized_actions", "authorized_paths")}}
    graph = StateGraph(WorkflowState)
    graph.add_node("validate_operation", lambda state: _validate_operation_binding(state, runtime_profile))
    graph.add_node("M1", _m1_observe)
    graph.add_node("M2", _m2_validate)
    graph.add_node("M3", _m3_review)
    graph.add_node("M4", _m4_reconcile)
    graph.add_node("M5", lambda state: _m5_request_host_action(state, runtime_profile))
    graph.add_node("M6", _m6_verify_host_receipt)
    graph.add_node("M7", lambda state: _m7_settlement_request(state, runtime_profile))
    graph.add_edge(START, "validate_operation")
    graph.add_conditional_edges(
        "validate_operation",
        _start_activity,
        {**{activity: activity for activity in ACTIVITY_IDS}, END: END},
    )
    graph.add_conditional_edges(
        "M1",
        lambda state: "M2" if state.get("status") == "CONTINUE" else END,
        {"M2": "M2", END: END},
    )
    graph.add_conditional_edges(
        "M2",
        lambda state: "M3" if state.get("status") == "CONTINUE" else END,
        {"M3": "M3", END: END},
    )
    graph.add_conditional_edges(
        "M3",
        lambda state: "M4" if state.get("status") == "CONTINUE" else END,
        {"M4": "M4", END: END},
    )
    graph.add_conditional_edges(
        "M4",
        lambda state: "M5" if state.get("status") == "CONTINUE" else END,
        {"M5": "M5", END: END},
    )
    graph.add_conditional_edges(
        "M5",
        lambda state: "M6" if state.get("status") == "CONTINUE" else END,
        {"M6": "M6", END: END},
    )
    graph.add_conditional_edges(
        "M6",
        lambda state: "M7" if state.get("status") == "CONTINUE" else END,
        {"M7": "M7", END: END},
    )
    graph.add_edge("M7", END)
    return graph.compile()


__all__ = ["ACTIVITY_IDS", "M1_M7_SOURCE_SHA256", "WorkflowContractError", "WorkflowState", "build_m1_m7_graph", "load_m1_m7_contracts"]
