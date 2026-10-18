"""SCRUM-842 Loop scheduled operation integration/harness layer (G2).

INTEGRATE + HARNESS ONLY: the harness emits a bound operation envelope per
Loop firing (stable tick/activity ID, envelope fields per the frozen SCRUM-841
manifest), invokes/resumes the same persistent frozen LangGraph M1-M7 run,
validates the structured verdict + exact readback, and invokes native
LoopManager settlement exactly once. Hermes core is out of scope (read-only
reference); no core module is imported or modified here.
"""
from __future__ import annotations

from pathlib import Path
import json
import shutil

import pytest

try:
    from jsonschema import Draft202012Validator
    _JSONSCHEMA_AVAILABLE = True
except ImportError:  # pragma: no cover
    Draft202012Validator = None  # type: ignore[assignment,misc]
    _JSONSCHEMA_AVAILABLE = False

try:
    from tools.node_architect.loop_scheduled_operation_harness import (
        OPERATION_ENVELOPE_FIELDS,
        emit_operation_envelope,
        invoke_or_resume,
        validate_verdict_and_readback,
    )
    from tools.node_architect.loop_settlement_reconciler import LoopSettlementReconciler
    _HARNESS_AVAILABLE = True
except ImportError:  # RED phase: harness does not exist yet
    OPERATION_ENVELOPE_FIELDS = ()
    emit_operation_envelope = None  # type: ignore[assignment,misc]
    invoke_or_resume = None  # type: ignore[assignment,misc]
    validate_verdict_and_readback = None  # type: ignore[assignment,misc]
    LoopSettlementReconciler = None  # type: ignore[assignment,misc]
    _HARNESS_AVAILABLE = False

try:
    from tools.node_architect.m1_m7_agent_workflow import (
        M1_M7_SOURCE_SHA256,
        build_m1_m7_graph,
        load_m1_m7_contracts,
    )
    _M1M7_AVAILABLE = True
except ImportError:  # langgraph is an optional isolated dependency
    M1_M7_SOURCE_SHA256 = "sha256:" + "0" * 64
    build_m1_m7_graph = None  # type: ignore[assignment,misc]
    load_m1_m7_contracts = None  # type: ignore[assignment,misc]
    _M1M7_AVAILABLE = False

ROOT = Path(__file__).resolve().parents[1]


def _sandbox_root(tmp_path: Path) -> Path:
    """Mirror a minimal repo with the frozen SCRUM-841 contract files."""
    root = tmp_path / "repo"
    refs = [
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


def _m5_inputs(operation, action_id="modify_approved_files"):
    """A full M1-M6 input set that drives the graph to the M7 settlement."""
    activation = {
        "artifact_type": "g2-activation-receipt", "activation_state": "ACTIVE",
        "approval_request_id": "g2_scrum-842_host", "approval_request_actor_id": "Nhat Nguyen Quang",
        "validated_actor_id": "Nhat Nguyen Quang",
        "approval_validation": {
            "artifact_type": "gate-approval-validation", "outcome": "VALID", "approval_valid": True,
            "approval_request_ref": "g2_scrum-842_host",
            "task_id": operation["task_id"], "repository": operation["repository"],
            "base_sha": operation["base_sha"], "head_sha": operation["head_sha"],
            "working_branch": operation["working_branch"], "scope_hash": operation["scope_hash"],
            "risk_class": "R1", "authorized_actions": [action_id],
            "validation_digest": "sha256:" + "f" * 64,
            "execution_authority_granted": False, "merge_authority_granted": False,
            "deployment_authority_granted": False, "production_authority_granted": False,
        },
        "approval_validation_digest": "sha256:" + "f" * 64,
        "envelope_digest": "sha256:" + "1" * 64,
        "expires_at": "2099-12-31T23:59:59Z", "execution_started": False,
        "task_id": operation["task_id"], "repository": operation["repository"],
        "run_id": operation["run_id"], "branch": operation["working_branch"],
        "base_sha": operation["base_sha"], "head_sha": operation["head_sha"],
        "scope_hash": operation["scope_hash"], "risk_class": "R1", "gate": "G2_EXECUTION",
        "authorized_actions": [action_id],
        "authorized_paths": ["core/node-architect/scrum841-m1-m7-agent-workflow-r1.json"],
    }
    action = {
        "action": action_id,
        "idempotency_key": f"{operation['operation_id']}:M5:write-1",
        "payload_digest": "sha256:" + "e" * 64,
        "target_ref": "core/node-architect/scrum841-m1-m7-agent-workflow-r1.json",
    }
    host_request = {
        **action, "request_type": "host_action_request",
        "task_id": operation["task_id"], "repository": operation["repository"],
        "run_id": operation["run_id"], "operation_id": operation["operation_id"],
        "activity_id": operation["activity_id"], "base_sha": operation["base_sha"],
        "head_sha": operation["head_sha"], "working_branch": operation["working_branch"],
        "scope_hash": operation["scope_hash"], "runtime_plan_digest": operation["runtime_plan_digest"],
        "effect_performed": False, "authority_granted": False,
    }
    host_receipt = {
        **host_request, "status": "VERIFIED", "readback_status": "VERIFIED",
        "readback_target": action["target_ref"], "readback_digest": "sha256:" + "2" * 64,
        "validation_outcome": "PASS", "validation_digest": "sha256:" + "3" * 64,
    }
    capability = {
        **operation, "artifact_type": "native-loop-capability-receipt", "qualified": True,
        "native_loop_owner": "hermes_host", "settlement_allowed": True,
        "receipt_digest": "sha256:" + "4" * 64,
    }
    mailbox_capability = {
        **operation, "artifact_type": "m7-mailbox-notification-capability-receipt",
        "qualified": True, "single_executor_mailbox": True, "mailbox_patch_allowed": True,
        "controller_notification_allowed": True,
        "executor_mailbox_ref": "taskcontroller://executor/current",
        "controller_notification_target": "controller://bound",
        "receipt_digest": "sha256:" + "5" * 64,
    }
    return {
        "observer_qualified": True,
        "observer_receipt": {**operation, "classification": "CLEAR"},
        "action_request": action,
        "g2_activation_receipt": activation,
        "prior_host_action_requests": [host_request],
        "host_action_receipt": host_receipt,
        "settlement_capability_receipt": capability,
        "mailbox_notification_capability": mailbox_capability,
    }


# --------------------------------------------------------------------------
# Envelope emission
# --------------------------------------------------------------------------

def test_emit_envelope_has_all_manifest_fields_and_stable_tick_id(tmp_path):
    root = _sandbox_root(tmp_path)
    first = emit_operation_envelope(root, run_id="run-842-1", tick=7)
    second = emit_operation_envelope(root, run_id="run-842-1", tick=7)

    assert set(OPERATION_ENVELOPE_FIELDS) == {
        "task_id", "repository", "run_id", "operation_id", "activity_id",
        "base_sha", "head_sha", "working_branch", "scope_hash",
        "runtime_plan_digest", "protocol_version", "continuation_ref", "cursor",
    }
    assert all(isinstance(first[f], str) and first[f] for f in OPERATION_ENVELOPE_FIELDS if f != "cursor")
    assert isinstance(first["cursor"], dict)
    # stable tick/activity identity: same tick -> identical envelope
    assert first == second
    # different tick -> different activity/operation ID
    other = emit_operation_envelope(root, run_id="run-842-1", tick=8)
    assert other["activity_id"] != first["activity_id"]
    assert other["operation_id"] != first["operation_id"]


def test_emit_envelope_binds_frozen_profile_identity(tmp_path):
    _require_harness()
    _require_langgraph()
    root = _sandbox_root(tmp_path)
    manifest, profile = load_m1_m7_contracts(root)
    envelope = emit_operation_envelope(root, run_id="run-842-2", tick=1)

    assert envelope["task_id"] == profile["task_id"] == "SCRUM-841"
    assert envelope["repository"] == profile["repository"]
    assert envelope["base_sha"] == profile["base_sha"]
    assert envelope["working_branch"] == profile["working_branch"]
    assert envelope["scope_hash"] == profile["scope_hash"]
    assert envelope["runtime_plan_digest"] == profile["runtime_plan_digest"]
    assert envelope["head_sha"] == envelope["base_sha"]
    assert envelope["protocol_version"] == "dw.taskcontroller.continuation/v1"
    assert envelope["continuation_ref"].startswith("sha256:")
    assert len(envelope["continuation_ref"]) == 71
    assert envelope["cursor"]["controller_seq"] >= 0
    assert envelope["cursor"]["executor_seq"] >= 0
    assert manifest["workflow_id"] == "scrum841-m1-m7-agent-workflow-r1"


# --------------------------------------------------------------------------
# Invoke / resume of the frozen persistent run
# --------------------------------------------------------------------------

def _require_harness():
    if not _HARNESS_AVAILABLE:
        pytest.skip("loop scheduled operation harness not importable (RED phase)")


def _require_langgraph():
    if not _M1M7_AVAILABLE:
        pytest.skip("langgraph backend not installed (optional isolated dependency)")


def test_invoke_without_observer_holds_at_m1_suspended(tmp_path):
    _require_harness()
    _require_langgraph()
    root = _sandbox_root(tmp_path)
    envelope = emit_operation_envelope(root, run_id="run-842-invoke-1", tick=1)
    result = invoke_or_resume(
        root,
        operation_envelope=envelope,
        inputs={"observer_qualified": False, "observer_receipt": None},
        checkpoint_store_ref=".gwc/tasks/SCRUM-842/g2/checkpoints/run-842-invoke-1.json",
        checkpoint_expected_revision=0,
    )
    assert result["verdict"]["status"] == "HOLD"
    assert result["verdict"]["reason_code"] == "OBSERVER_UNQUALIFIED"
    assert result["verdict"]["current_activity"] == "M1"
    assert result["settlement_requests"] == []
    assert result["checkpoint_persistence"]["outcome"] == "PASS"


def test_resume_same_run_reuses_checkpoint_and_advances_revision(tmp_path):
    _require_harness()
    _require_langgraph()
    root = _sandbox_root(tmp_path)
    envelope = emit_operation_envelope(root, run_id="run-842-resume-1", tick=2)
    store_ref = ".gwc/tasks/SCRUM-842/g2/checkpoints/run-842-resume-1.json"
    invoke_or_resume(
        root, operation_envelope=envelope,
        inputs={"observer_qualified": False, "observer_receipt": None},
        checkpoint_store_ref=store_ref, checkpoint_expected_revision=0,
    )
    path = root / store_ref
    store = json.loads(path.read_text(encoding="utf-8"))
    assert store["revision"] == 1
    record = next(iter(store["checkpoints"].values()))
    assert record["state"]["task_id"] == "SCRUM-841"
    assert record["run_id"] == "run-842-resume-1"
    assert "browser_url" not in record["state"]
    assert "browser_session" not in record["state"]

    # resume the same persistent run with identical inputs: no duplicate
    # checkpoint, no revision bump (exactly-once checkpoint replay)
    resumed = invoke_or_resume(
        root, operation_envelope=envelope,
        inputs={"observer_qualified": False, "observer_receipt": None},
        checkpoint_store_ref=store_ref, checkpoint_expected_revision=1,
    )
    assert resumed["verdict"]["status"] == "HOLD"
    assert resumed["checkpoint_persistence"]["outcome"] == "IDEMPOTENT_REPLAY"
    assert json.loads(path.read_text(encoding="utf-8"))["revision"] == 1

    # resume with changed inputs (qualified observer) advances the CAS revision
    advanced = invoke_or_resume(
        root, operation_envelope=envelope,
        inputs=_m5_inputs(envelope),
        checkpoint_store_ref=store_ref, checkpoint_expected_revision=1,
    )
    assert advanced["verdict"]["status"] == "WAIT"
    assert advanced["checkpoint_persistence"]["outcome"] == "PASS"
    assert json.loads(path.read_text(encoding="utf-8"))["revision"] == 2


def test_full_m1_m7_run_emits_exactly_one_settlement_request(tmp_path):
    _require_harness()
    _require_langgraph()
    root = _sandbox_root(tmp_path)
    envelope = emit_operation_envelope(root, run_id="run-842-full-1", tick=3)
    result = invoke_or_resume(
        root,
        operation_envelope=envelope,
        inputs=_m5_inputs(envelope),
        checkpoint_store_ref=".gwc/tasks/SCRUM-842/g2/checkpoints/run-842-full-1.json",
        checkpoint_expected_revision=0,
    )
    assert result["verdict"]["status"] == "WAIT"
    assert result["verdict"]["reason_code"] == "M7_SETTLEMENT_REQUESTED"
    assert len(result["settlement_requests"]) == 1
    settlement = result["settlement_requests"][0]
    assert settlement["request_type"] == "native_loop_settlement_request"
    assert settlement["requested_settlement"] == "complete"
    assert settlement["idempotency_key"] == f"{envelope['operation_id']}:M7:settlement"
    assert settlement["settled"] is False
    assert settlement["authority_granted"] is False
    assert result["verdict"]["current_activity"] == "M7"


# --------------------------------------------------------------------------
# Verdict + exact readback validation
# --------------------------------------------------------------------------

def test_validate_verdict_and_readback_passes_on_verified_result(tmp_path):
    _require_harness()
    _require_langgraph()
    root = _sandbox_root(tmp_path)
    envelope = emit_operation_envelope(root, run_id="run-842-val-1", tick=4)
    result = invoke_or_resume(
        root,
        operation_envelope=envelope,
        inputs=_m5_inputs(envelope),
        checkpoint_store_ref=".gwc/tasks/SCRUM-842/g2/checkpoints/run-842-val-1.json",
        checkpoint_expected_revision=0,
    )
    validated = validate_verdict_and_readback(result, envelope)
    assert validated["outcome"] == "PASS"
    assert validated["readback_verified"] is True
    assert validated["verdict"] == "WAIT"
    assert validated["reason_code"] == "M7_SETTLEMENT_REQUESTED"


def test_validate_fails_closed_on_envelope_binding_drift(tmp_path):
    _require_harness()
    _require_langgraph()
    root = _sandbox_root(tmp_path)
    envelope = emit_operation_envelope(root, run_id="run-842-drift-1", tick=5)
    result = invoke_or_resume(
        root,
        operation_envelope=envelope,
        inputs=_m5_inputs(envelope),
        checkpoint_store_ref=".gwc/tasks/SCRUM-842/g2/checkpoints/run-842-drift-1.json",
        checkpoint_expected_revision=0,
    )
    drifted = dict(envelope)
    drifted["base_sha"] = "0" * 40
    validated = validate_verdict_and_readback(result, drifted)
    assert validated["outcome"] == "FAIL"
    assert validated["readback_verified"] is False
    assert validated["reason_code"] == "VERDICT_ENVELOPE_BINDING_DRIFT"


def test_validate_rejects_forbidden_checkpoint_bindings(tmp_path):
    _require_harness()
    _require_langgraph()
    root = _sandbox_root(tmp_path)
    envelope = emit_operation_envelope(root, run_id="run-842-forbid-1", tick=6)
    result = invoke_or_resume(
        root,
        operation_envelope=envelope,
        inputs={"observer_qualified": False, "observer_receipt": None},
        checkpoint_store_ref=".gwc/tasks/SCRUM-842/g2/checkpoints/run-842-forbid-1.json",
        checkpoint_expected_revision=0,
    )
    # Tamper the readback projection inside the checkpoint store: browser binding
    # must never appear in graph checkpoints.
    store_path = root / ".gwc/tasks/SCRUM-842/g2/checkpoints/run-842-forbid-1.json"
    store = json.loads(store_path.read_text(encoding="utf-8"))
    record = next(iter(store["checkpoints"].values()))
    record["state"]["browser_url"] = "chrome://injected"
    store_path.write_text(json.dumps(store, indent=2) + "\n", encoding="utf-8")
    result["checkpoint_projection"] = record["state"]
    validated = validate_verdict_and_readback(result, envelope)
    assert validated["outcome"] == "FAIL"
    assert validated["reason_code"] == "CHECKPOINT_FORBIDDEN_BINDING"


# --------------------------------------------------------------------------
# Exactly-once native LoopManager settlement
# --------------------------------------------------------------------------

def test_settlement_reconciler_invokes_native_exactly_once(tmp_path):
    _require_harness()
    calls: list[dict] = []

    def native_settlement(request):
        calls.append(dict(request))
        return {
            "status": "VERIFIED",
            "settled": True,
            "settlement_id": f"settled-{request['idempotency_key']}",
            "readback_digest": "sha256:" + "9" * 64,
        }

    ledger = tmp_path / "settlement-ledger.json"
    reconciler = LoopSettlementReconciler(ledger)
    settlement = {
        "request_type": "native_loop_settlement_request",
        "idempotency_key": "op-842:1:M7:settlement",
        "requested_settlement": "complete",
        "activity_id": "tick-1",
    }
    first = reconciler.settle_exactly_once(settlement, native_settlement)
    second = reconciler.settle_exactly_once(settlement, native_settlement)

    assert first["outcome"] == "SETTLED"
    assert first["invoked"] is True
    assert second["outcome"] == "ALREADY_SETTLED"
    assert second["invoked"] is False
    assert len(calls) == 1  # native LoopManager settlement invoked exactly once


def test_settlement_reconciler_survives_reload_and_persists_receipt(tmp_path):
    _require_harness()
    native_results = [{"status": "VERIFIED", "settled": True, "readback_digest": "sha256:" + "8" * 64}]

    def native_settlement(request):
        return dict(native_results[0])

    ledger = tmp_path / "settlement-ledger.json"
    reconciler = LoopSettlementReconciler(ledger)
    settlement = {
        "request_type": "native_loop_settlement_request",
        "idempotency_key": "op-842:2:M7:settlement",
        "activity_id": "tick-2",
    }
    first = reconciler.settle_exactly_once(settlement, native_settlement)
    assert first["outcome"] == "SETTLED"
    assert json.loads(ledger.read_text(encoding="utf-8"))["settlements"]["op-842:2:M7:settlement"]["settled"] is True

    # fresh reconciler over the same ledger: replay is a no-op, no second call
    reloaded = LoopSettlementReconciler(ledger)
    replay = reloaded.settle_exactly_once(settlement, native_settlement)
    assert replay["outcome"] == "ALREADY_SETTLED"
    assert replay["receipt"]["settled"] is True


def test_settlement_reconciler_fails_closed_without_idempotency_key(tmp_path):
    _require_harness()
    ledger = tmp_path / "settlement-ledger.json"
    reconciler = LoopSettlementReconciler(ledger)
    with pytest.raises(ValueError, match="IDEMPOTENCY_KEY"):
        reconciler.settle_exactly_once(
            {"request_type": "native_loop_settlement_request", "requested_settlement": "complete"},
            lambda request: {"status": "VERIFIED"},
        )


def test_settlement_reconciler_does_not_record_unverified_native_result(tmp_path):
    _require_harness()
    ledger = tmp_path / "settlement-ledger.json"
    reconciler = LoopSettlementReconciler(ledger)
    settlement = {
        "request_type": "native_loop_settlement_request",
        "idempotency_key": "op-842:3:M7:settlement",
        "activity_id": "tick-3",
    }
    with pytest.raises(ValueError, match="UNVERIFIED"):
        reconciler.settle_exactly_once(
            settlement,
            lambda request: {"status": "FAILED", "settled": False},
        )
    # nothing recorded: no ledger file (or an empty settlement map if one exists)
    if ledger.exists():
        assert json.loads(ledger.read_text(encoding="utf-8"))["settlements"] == {}


# --------------------------------------------------------------------------
# Manifest + schema conformance
# --------------------------------------------------------------------------

def test_scrum842_manifest_and_schema_validate(tmp_path):
    if not _JSONSCHEMA_AVAILABLE:
        pytest.skip("jsonschema not installed")
    manifest_path = ROOT / "core/node-architect/scrum842-loop-scheduled-operation-r1.json"
    schema_path = ROOT / "schemas/node-architect/scrum842-loop-scheduled-operation.schema.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    errors = list(Draft202012Validator(schema).iter_errors(manifest))
    assert errors == []
    assert manifest["task_id"] == "SCRUM-842"
    assert manifest["hosted_workflow_id"] == "scrum841-m1-m7-agent-workflow-r1"
    assert manifest["exactly_once_settlement"] is True
    assert manifest["native_loop_owner"] == "hermes_host"
    assert manifest["graph_settles_native_loop"] is False
    assert manifest["graph_owns_scheduler_state"] is False