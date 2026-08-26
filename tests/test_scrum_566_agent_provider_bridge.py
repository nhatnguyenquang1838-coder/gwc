from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

from tools.node_architect.ai_agent_adapter import ProviderUnavailable


def _module(name: str):
    spec = importlib.util.find_spec(name)
    assert spec is not None, f"{name} must exist"
    return importlib.import_module(name)


def _request() -> dict:
    return {
        "schema_version": "1.0",
        "run_id": "scrum-566-w11",
        "task_id": "SCRUM-566",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "preprod_base_sha": "a" * 40,
        "working_branch": "chatgpt/scrum-566-agent-runtime-corrective",
        "scope_hash": "sha256:" + "b" * 64,
        "graph_revision": "graph-w11",
        "policy_revision": "policy-w11",
        "allowed_paths": ["tools/node_architect/scratch/foo.py"],
        "prohibited_paths": [],
        "authorized_actions": ["modify_approved_files"],
        "validation_commands": ["python -m pytest tests/scratch"],
        "idempotency_key": "scrum-566-w11-idem",
    }


class RecordingProvider:
    name = "recording-provider"

    def __init__(self, *, unavailable: bool = False):
        self.unavailable = unavailable
        self.packs = []

    def run(self, pack):
        self.packs.append(pack)
        if self.unavailable:
            raise ProviderUnavailable("offline")
        return {
            "changed_paths": ["tools/node_architect/scratch/foo.py"],
            "recorded_actions": ["modify_approved_files"],
            "validation_passed": True,
            "next_node_id": "attacker-selected-node",
            "authority_granted": True,
        }


def _source() -> dict:
    return {
        "status": "SOURCE_RESOLVED_EVALUATOR",
        "runtime_eligible": True,
        "reason_code": "SEMANTIC_EVALUATOR_BOUND",
        "evaluator_path": "tools/node_architect/ai_agent_adapter.py",
        "descriptor_path": "core/node-architect/node-catalog/repo_delivery/ai-assisted.node.json",
    }


def _node() -> dict:
    return {
        "id": "repo_delivery.ai-assisted-execution",
        "family": "repo_delivery",
        "version": "1.0.0",
        "runtime_executable": True,
        "effect_class": "write_scoped",
    }


def test_agent_provider_bridge_is_an_explicit_semantic_binding():
    bridge = _module("tools.node_architect.agent_provider_bridge")
    dispatcher = _module("tools.node_architect.semantic_dispatcher")
    provider = RecordingProvider()
    binding = bridge.build_agent_provider_binding(
        node_id=_node()["id"],
        evaluator_path="tools/node_architect/ai_agent_adapter.py",
        request=_request(),
        provider=provider,
        idempotency_store={},
    )

    result = dispatcher.dispatch_semantic_node(
        _node(),
        _source(),
        {"objective": "repair CI"},
        bindings={binding.node_id: binding},
    )

    assert result["status"] == "SEMANTIC_EXECUTED"
    assert result["result"]["runtime_disposition"] == "CONTINUE"
    assert result["result"]["provider_result"]["terminal_outcome"] == "SUCCESS"
    assert provider.packs[0].semantic_input_digest.startswith("sha256:")
    assert "next_node_id" not in result["result"]["provider_result"]
    assert result["result"]["provider_result"]["g3_g4_g5_authority_granted"] is False


def test_agent_provider_bridge_binds_node_input_into_pack_digest():
    bridge = _module("tools.node_architect.agent_provider_bridge")
    provider_a = RecordingProvider()
    provider_b = RecordingProvider()
    binding_a = bridge.build_agent_provider_binding(
        node_id=_node()["id"],
        evaluator_path="tools/node_architect/ai_agent_adapter.py",
        request=_request(),
        provider=provider_a,
        idempotency_store={},
    )
    binding_b = bridge.build_agent_provider_binding(
        node_id=_node()["id"],
        evaluator_path="tools/node_architect/ai_agent_adapter.py",
        request=_request(),
        provider=provider_b,
        idempotency_store={},
    )

    binding_a.handler({"objective": "A"})
    binding_b.handler({"objective": "B"})

    assert provider_a.packs[0].semantic_input_digest != provider_b.packs[0].semantic_input_digest
    assert provider_a.packs[0].content_digest != provider_b.packs[0].content_digest


def test_agent_provider_failure_blocks_lifecycle_before_readback(tmp_path: Path):
    bridge = _module("tools.node_architect.agent_provider_bridge")
    lifecycle = _module("tools.node_architect.semantic_lifecycle")
    provider = RecordingProvider(unavailable=True)
    binding = bridge.build_agent_provider_binding(
        node_id=_node()["id"],
        evaluator_path="tools/node_architect/ai_agent_adapter.py",
        request=_request(),
        provider=provider,
        idempotency_store={},
    )
    readback_called = False

    def readback(node, result, event):
        nonlocal readback_called
        readback_called = True
        return {"status": "VERIFIED"}

    event = {
        "task_id": "SCRUM-566",
        "run_id": "run-w11",
        "gate": "G2_EXECUTION",
        "scenario": "ci_failure",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "branch": "chatgpt/scrum-566-agent-runtime-corrective",
        "base_sha": "a" * 40,
        "exact_revision": "b" * 40,
        "scope_hash": "sha256:" + "c" * 64,
        "idempotency_key": "scrum-566-w11-lifecycle",
        "occurred_at": "2026-08-26T14:30:00Z",
        "input_payload": {"objective": "repair CI"},
    }

    result = lifecycle.run_semantic_route_event(
        event,
        {"nodes": [_node()]},
        {"edges": []},
        bindings={binding.node_id: binding},
        readback_handlers={binding.node_id: readback},
        source_root=tmp_path,
        evidence_root=tmp_path / "evidence",
        source_resolver=lambda node, *, root: _source(),
    )

    assert result["status"] == "SEMANTIC_ROUTE_BLOCKED"
    assert result["reason_code"] == "AGENT_PROVIDER_FAIL_CLOSED"
    assert readback_called is False
    assert result["semantic_executed_node_ids"] == [_node()["id"]]
