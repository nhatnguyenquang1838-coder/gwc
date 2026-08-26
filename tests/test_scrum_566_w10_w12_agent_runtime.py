from __future__ import annotations

import importlib
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _module(name: str):
    spec = importlib.util.find_spec(name)
    assert spec is not None, f"{name} must exist"
    return importlib.import_module(name)


def _binding(side_effect="repository_write") -> dict:
    return {
        "node_id": "repo_delivery.scoped-file-write",
        "node_version": "1.0.0",
        "node_registry_revision": "registry-r1",
        "implementation_kind": "semantic_tool_callable",
        "implementation_ref": "fixture:handler",
        "binding_digest": "sha256:" + "1" * 64,
        "gates": ["G2_EXECUTION"],
        "entry_contract": ["g0_context", "g1_decision", "g2_envelope"],
        "readback_contract": {"required": True},
        "side_effect_class": side_effect,
        "authority_requirements": {"gate_authority_required": True, "node_grants_gate_authority": False},
        "checkpoint_contract": {"required": True, "suspension": {"suspendable": True}},
        "next_route_contract": {
            "pass": {"disposition": "continue", "reason": "next", "next_node": "repo_delivery.pr-blocker-check", "next_action": "pr_blocker_check", "next_gate": None},
            "blocked": {"disposition": "stop", "reason": "blocked", "next_node": None, "next_action": None, "next_gate": "G2_EXECUTION"},
            "pending": {"disposition": "wait", "reason": "wait", "next_node": "repo_delivery.scoped-file-write", "next_action": "repository_write", "next_gate": None},
            "retry": {"disposition": "retry", "reason": "retry", "next_node": "repo_delivery.scoped-file-write", "next_action": "repository_write", "next_gate": None},
        },
    }


def _event(**overrides) -> dict:
    value = {
        "schema_version": "1.0",
        "event_id": "evt-w10-1",
        "task_id": "SCRUM-566",
        "run_id": "run-w10",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "branch": "chatgpt/scrum-566-agent-runtime-corrective",
        "base_sha": "a" * 40,
        "head_sha": "b" * 40,
        "exact_revision": "b" * 40,
        "scope_hash": "sha256:" + "c" * 64,
        "gate": "G2_EXECUTION",
        "requested_action": "repository_write",
        "profile_revision": "profile-r1",
        "graph_revision": "graph-r1",
        "node_registry_revision": "registry-r1",
        "policy_revision": "policy-r1",
        "idempotency_key": "idem-w10",
        "occurred_at": "2026-08-26T16:00:00Z",
        "input_payload": {
            "g0_context": {"ok": True},
            "g1_decision": {"ok": True},
            "g2_envelope": {"ok": True},
        },
        "live_agent_event": True,
        "synthetic": False,
    }
    value.update(overrides)
    return value


def _authority(**overrides) -> dict:
    expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    value = {
        "authority_id": "auth-scrum-566-w12",
        "source": "explicit_user_scoped_branch_write",
        "task_id": "SCRUM-566",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "branch": "chatgpt/scrum-566-agent-runtime-corrective",
        "head_sha": "b" * 40,
        "scope_hash": "sha256:" + "c" * 64,
        "gate": "G2_EXECUTION",
        "allowed_actions": ["repository_write"],
        "writer_target": "repo:nhatnguyenquang1838-coder/gwc:branch:chatgpt/scrum-566-agent-runtime-corrective",
        "fencing_token": "fence-1",
        "expires_at": expiry,
        "later_gate_authority": False,
    }
    value.update(overrides)
    return value


def _semantic_handler(binding, event):
    return {
        "outcome": "PASS",
        "reason_code": "FIXTURE_SEMANTIC_PASS",
        "requested_effects": [{"action": event["requested_action"], "side_effect_class": binding["side_effect_class"], "payload": {"path": "scratch.json"}}],
        "proposed_effects": [],
        "executed_effects": [],
        "next_contract": binding["next_route_contract"]["pass"],
        "implementation_invoked": True,
        "semantic_execution": True,
        "invocation_digest": "sha256:" + "2" * 64,
    }


def test_shadow_and_authoritative_share_semantic_handler_but_shadow_never_writes(tmp_path: Path):
    runtime = _module("tools.node_architect.semantic_agent_runtime")
    semantic_calls = []
    write_calls = []

    def semantic(binding, event):
        semantic_calls.append(event["event_id"])
        return _semantic_handler(binding, event)

    def write(effect, event, authority):
        write_calls.append(effect)
        return {"status": "APPLIED", "effect_ref": "write-1"}

    shadow = runtime.execute_semantic_node_lifecycle(
        event=_event(event_id="shadow-1"),
        binding=_binding(),
        mode="shadow_readonly",
        semantic_handlers={"fixture:handler": semantic},
        capability_handlers={"repository_write": write},
        readback_handler=lambda *args: {"status": "VERIFIED", "effect_ref": "none"},
        evidence_root=tmp_path,
        state=runtime.RuntimeExecutionState(),
    )
    assert shadow["status"] == "SEMANTIC_NODE_COMPLETE"
    assert shadow["requested_effects"]
    assert shadow["proposed_effects"]
    assert shadow["executed_effects"] == []
    assert shadow["authority_granted"] is False
    assert write_calls == []

    authoritative = runtime.execute_semantic_node_lifecycle(
        event=_event(event_id="auth-1", idempotency_key="auth-idem"),
        binding=_binding(),
        mode="authoritative",
        authority=_authority(),
        semantic_handlers={"fixture:handler": semantic},
        capability_handlers={"repository_write": write},
        readback_handler=lambda *args: {"status": "VERIFIED", "effect_ref": "write-1"},
        evidence_root=tmp_path,
        state=runtime.RuntimeExecutionState(),
    )
    assert authoritative["status"] == "SEMANTIC_NODE_COMPLETE"
    assert authoritative["authority_granted"] is True
    assert authoritative["executed_effects"][0]["effect_ref"] == "write-1"
    assert len(semantic_calls) == 2
    assert len(write_calls) == 1


def test_authoritative_missing_or_drifted_authority_fails_before_mutation(tmp_path: Path):
    runtime = _module("tools.node_architect.semantic_agent_runtime")
    writes = []
    kwargs = dict(
        event=_event(), binding=_binding(), mode="authoritative",
        semantic_handlers={"fixture:handler": _semantic_handler},
        capability_handlers={"repository_write": lambda *args: writes.append(args)},
        readback_handler=lambda *args: {"status": "VERIFIED"},
        evidence_root=tmp_path,
    )
    out = runtime.execute_semantic_node_lifecycle(**kwargs, authority=None, state=runtime.RuntimeExecutionState())
    assert out["status"] == "SEMANTIC_NODE_BLOCKED"
    assert out["reason_code"] == "AUTHORITY_MISSING"
    assert writes == []

    for authority in (
        _authority(head_sha="d" * 40),
        _authority(allowed_actions=["other"]),
        _authority(scope_hash="sha256:" + "e" * 64),
        _authority(branch="other"),
    ):
        out = runtime.execute_semantic_node_lifecycle(**kwargs, authority=authority, state=runtime.RuntimeExecutionState())
        assert out["status"] == "SEMANTIC_NODE_BLOCKED"
        assert writes == []


def test_route_provider_or_ci_flags_never_substitute_for_authority(tmp_path: Path):
    runtime = _module("tools.node_architect.semantic_agent_runtime")
    event = _event(input_payload={
        **_event()["input_payload"],
        "route_authority_granted": True,
        "provider_authority_granted": True,
        "ci_passed": True,
    })
    out = runtime.execute_semantic_node_lifecycle(
        event=event, binding=_binding(), mode="authoritative", authority=None,
        semantic_handlers={"fixture:handler": _semantic_handler},
        capability_handlers={"repository_write": lambda *args: {"status": "APPLIED"}},
        readback_handler=lambda *args: {"status": "VERIFIED"},
        evidence_root=tmp_path, state=runtime.RuntimeExecutionState(),
    )
    assert out["reason_code"] == "AUTHORITY_MISSING"


def test_authoritative_effect_requires_canonical_readback_before_success(tmp_path: Path):
    runtime = _module("tools.node_architect.semantic_agent_runtime")
    out = runtime.execute_semantic_node_lifecycle(
        event=_event(), binding=_binding(), mode="authoritative", authority=_authority(),
        semantic_handlers={"fixture:handler": _semantic_handler},
        capability_handlers={"repository_write": lambda *args: {"status": "APPLIED", "effect_ref": "write-1"}},
        readback_handler=lambda *args: {"status": "MISMATCH", "reason_code": "CANONICAL_READBACK_MISMATCH"},
        evidence_root=tmp_path, state=runtime.RuntimeExecutionState(),
    )
    assert out["status"] == "SEMANTIC_NODE_BLOCKED"
    assert out["reason_code"] == "CANONICAL_READBACK_MISMATCH"
    assert out["canonical_readback_verified"] is False


def test_single_writer_fencing_rejects_competing_authoritative_writer(tmp_path: Path):
    runtime = _module("tools.node_architect.semantic_agent_runtime")
    state = runtime.RuntimeExecutionState()
    common = dict(
        binding=_binding(), mode="authoritative",
        semantic_handlers={"fixture:handler": _semantic_handler},
        capability_handlers={"repository_write": lambda *args: {"status": "APPLIED", "effect_ref": "ok"}},
        readback_handler=lambda *args: {"status": "VERIFIED", "effect_ref": "ok"},
        evidence_root=tmp_path, state=state,
    )
    first = runtime.execute_semantic_node_lifecycle(
        event=_event(event_id="writer-1", idempotency_key="writer-idem-1"), authority=_authority(fencing_token="fence-A"), **common
    )
    assert first["status"] == "SEMANTIC_NODE_COMPLETE"
    second = runtime.execute_semantic_node_lifecycle(
        event=_event(event_id="writer-2", idempotency_key="writer-idem-2"), authority=_authority(fencing_token="fence-B"), **common
    )
    assert second["status"] == "SEMANTIC_NODE_BLOCKED"
    assert second["reason_code"] == "AUTHORITATIVE_WRITER_FENCED"


def test_read_only_fanout_does_not_acquire_writer_fence(tmp_path: Path):
    runtime = _module("tools.node_architect.semantic_agent_runtime")
    state = runtime.RuntimeExecutionState()
    binding = _binding(side_effect="read_only")

    def read_semantic(binding, event):
        result = _semantic_handler(binding, event)
        result["requested_effects"] = []
        return result

    for idx in range(2):
        out = runtime.execute_semantic_node_lifecycle(
            event=_event(event_id=f"read-{idx}", idempotency_key=f"read-idem-{idx}"),
            binding=binding, mode="authoritative", authority=_authority(fencing_token=f"read-{idx}"),
            semantic_handlers={"fixture:handler": read_semantic}, capability_handlers={},
            readback_handler=lambda *args: {"status": "VERIFIED"}, evidence_root=tmp_path, state=state,
        )
        assert out["status"] == "SEMANTIC_NODE_COMPLETE"
    assert state.writer_fences == {}


def test_next_gate_is_boundary_not_automatic_advance(tmp_path: Path):
    runtime = _module("tools.node_architect.semantic_agent_runtime")

    def semantic(binding, event):
        result = _semantic_handler(binding, event)
        result["requested_effects"] = []
        result["next_contract"] = {"disposition": "stop", "reason": "need G3", "next_node": None, "next_action": None, "next_gate": "G3_PR"}
        return result

    out = runtime.execute_semantic_node_lifecycle(
        event=_event(), binding=_binding(side_effect="read_only"), mode="shadow_readonly",
        semantic_handlers={"fixture:handler": semantic}, capability_handlers={},
        readback_handler=lambda *args: {"status": "VERIFIED"}, evidence_root=tmp_path, state=runtime.RuntimeExecutionState(),
    )
    assert out["status"] == "SEMANTIC_NODE_COMPLETE"
    assert out["next_route"]["next_gate"] == "G3_PR"
    assert out["next_route"]["gate_authority_required"] is True
    assert out["automatic_gate_advance"] is False


def test_pending_checkpoint_is_revision_bound_and_stale_resume_fails(tmp_path: Path):
    runtime = _module("tools.node_architect.semantic_agent_runtime")

    def pending(binding, event):
        return {
            "outcome": "PENDING", "reason_code": "CI_WAIT", "requested_effects": [],
            "next_contract": binding["next_route_contract"]["pending"],
            "implementation_invoked": True, "semantic_execution": True,
            "invocation_digest": "sha256:" + "4" * 64,
        }

    state = runtime.RuntimeExecutionState()
    out = runtime.execute_semantic_node_lifecycle(
        event=_event(event_id="pending-1"), binding=_binding(side_effect="read_only"), mode="shadow_readonly",
        semantic_handlers={"fixture:handler": pending}, capability_handlers={},
        readback_handler=lambda *args: {"status": "VERIFIED"}, evidence_root=tmp_path, state=state,
    )
    assert out["status"] == "SEMANTIC_NODE_SUSPENDED"
    checkpoint = out["checkpoint"]
    assert checkpoint["head_sha"] == "b" * 40
    assert checkpoint["binding_digest"] == _binding()["binding_digest"]

    resumed = runtime.resume_checkpoint(checkpoint, event=_event(event_id="resume", idempotency_key="resume-idem"), binding=_binding())
    assert resumed["status"] == "RESUME_ALLOWED"
    stale = runtime.resume_checkpoint(checkpoint, event=_event(head_sha="d" * 40, exact_revision="d" * 40), binding=_binding())
    assert stale["status"] == "RESUME_BLOCKED"
    assert stale["reason_code"] == "CHECKPOINT_REVISION_DRIFT"
