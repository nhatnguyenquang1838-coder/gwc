from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

from tools.node_architect.ai_agent_adapter import DeterministicFakeProvider, ProviderUnavailable


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


def _semantic_input(**overrides) -> dict:
    value = {
        "agent_boot_ref": "AGENTS.md@sha256:boot",
        "agent_instruction_digest": "sha256:" + "1" * 64,
        "head_sha": "b" * 40,
        "gate": "G2_EXECUTION",
        "requested_action": "modify_approved_files",
        "g0_g1_decision_ref": "g1-decision-42",
        "task_summary": "repair governed CI",
        "objective": "repair CI",
        "acceptance_criteria": ["tests pass", "readback verified"],
        "gate_node_route": ["G2:repo_delivery.ai-assisted-execution"],
        "plan_refs": ["plan://scrum-566/w11"],
        "node_id": "repo_delivery.ai-assisted-execution",
        "node_version": "1.0.0",
        "implementation_ref": "tools/node_architect/ai_agent_adapter.py",
        "profile_revision": "profile-w11",
        "node_registry_revision": "registry-w11",
        "provider_contract_revision": "provider-contract-v1",
    }
    value.update(overrides)
    return value


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


class RecordingValidationRunner:
    name = "recording-validation-runner"

    def __init__(self, *, exit_code: int = 0):
        self.exit_code = exit_code
        self.commands: list[tuple[str, str | None]] = []

    def run(self, command: str, *, cwd=None):
        self.commands.append((command, None if cwd is None else str(cwd)))
        return {
            "exit_code": self.exit_code,
            "stdout": "trusted validation output",
            "stderr": "" if self.exit_code == 0 else "trusted validation failure",
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


def _binding(*, provider=None, runner=None, registry=None, provider_name=None):
    bridge = _module("tools.node_architect.agent_provider_bridge")
    return bridge.build_agent_provider_binding(
        node_id=_node()["id"],
        evaluator_path="tools/node_architect/ai_agent_adapter.py",
        request=_request(),
        provider=provider,
        provider_name=provider_name,
        provider_registry=registry,
        validation_runner=runner,
        validation_root=".",
        idempotency_store={},
    )


def test_agent_provider_bridge_is_an_explicit_semantic_binding():
    dispatcher = _module("tools.node_architect.semantic_dispatcher")
    provider = RecordingProvider()
    runner = RecordingValidationRunner()
    binding = _binding(provider=provider, runner=runner)

    result = dispatcher.dispatch_semantic_node(
        _node(),
        _source(),
        _semantic_input(),
        bindings={binding.node_id: binding},
    )

    assert result["status"] == "SEMANTIC_EXECUTED"
    assert result["result"]["runtime_disposition"] == "CONTINUE"
    assert result["result"]["provider_result"]["terminal_outcome"] == "SUCCESS"
    assert result["result"]["trusted_validation_passed"] is True
    assert result["result"]["validation_evidence"][0]["exit_code"] == 0
    assert runner.commands == [("python -m pytest tests/scratch", ".")]
    assert provider.packs[0].semantic_input_digest.startswith("sha256:")
    assert "next_node_id" not in result["result"]["provider_result"]
    assert result["result"]["provider_result"]["g3_g4_g5_authority_granted"] is False


def test_agent_provider_bridge_complete_instruction_identity_is_bound():
    provider = RecordingProvider()
    binding = _binding(provider=provider, runner=RecordingValidationRunner())
    semantic = _semantic_input()

    binding.handler(semantic)
    pack = provider.packs[0]

    assert pack.preprod_base_sha == _request()["preprod_base_sha"]
    for field in (
        "head_sha",
        "gate",
        "requested_action",
        "g0_g1_decision_ref",
        "task_summary",
        "objective",
        "node_id",
        "node_version",
        "implementation_ref",
        "profile_revision",
        "node_registry_revision",
        "provider_contract_revision",
        "agent_boot_ref",
        "agent_instruction_digest",
    ):
        assert getattr(pack, field) == semantic[field]
    assert list(pack.acceptance_criteria) == semantic["acceptance_criteria"]
    assert list(pack.gate_node_route) == semantic["gate_node_route"]
    assert list(pack.plan_refs) == semantic["plan_refs"]


def test_agent_provider_bridge_semantic_identity_drift_changes_content_digest():
    identity_fields = (
        "head_sha",
        "gate",
        "requested_action",
        "g0_g1_decision_ref",
        "objective",
        "node_version",
        "implementation_ref",
        "profile_revision",
        "node_registry_revision",
        "provider_contract_revision",
        "agent_boot_ref",
        "agent_instruction_digest",
    )
    for field in identity_fields:
        provider_a = RecordingProvider()
        provider_b = RecordingProvider()
        _binding(provider=provider_a, runner=RecordingValidationRunner()).handler(_semantic_input())
        changed = _semantic_input(**{field: _semantic_input()[field] + "-changed"})
        _binding(provider=provider_b, runner=RecordingValidationRunner()).handler(changed)
        assert provider_a.packs[0].content_digest != provider_b.packs[0].content_digest, field

    for field in ("acceptance_criteria", "gate_node_route", "plan_refs"):
        provider_a = RecordingProvider()
        provider_b = RecordingProvider()
        _binding(provider=provider_a, runner=RecordingValidationRunner()).handler(_semantic_input())
        changed = _semantic_input(**{field: list(_semantic_input()[field]) + ["changed"]})
        _binding(provider=provider_b, runner=RecordingValidationRunner()).handler(changed)
        assert provider_a.packs[0].content_digest != provider_b.packs[0].content_digest, field


def test_agent_provider_bridge_requires_trusted_validation_runner_before_provider_call():
    dispatcher = _module("tools.node_architect.semantic_dispatcher")
    provider = RecordingProvider()
    binding = _binding(provider=provider, runner=None)

    result = dispatcher.dispatch_semantic_node(
        _node(), _source(), _semantic_input(), bindings={binding.node_id: binding}
    )

    assert provider.packs == []
    assert result["result"]["runtime_disposition"] == "BLOCK"
    assert result["result"]["reason_code"] == "AGENT_VALIDATION_RUNNER_UNAVAILABLE"


def test_agent_provider_bridge_trusted_validation_failure_overrides_provider_self_report():
    dispatcher = _module("tools.node_architect.semantic_dispatcher")
    provider = RecordingProvider()
    runner = RecordingValidationRunner(exit_code=7)
    binding = _binding(provider=provider, runner=runner)

    result = dispatcher.dispatch_semantic_node(
        _node(), _source(), _semantic_input(), bindings={binding.node_id: binding}
    )

    assert result["result"]["provider_result"]["terminal_outcome"] == "SUCCESS"
    assert result["result"]["runtime_disposition"] == "BLOCK"
    assert result["result"]["reason_code"] == "AGENT_VALIDATION_FAILED"
    assert result["result"]["trusted_validation_passed"] is False
    assert result["result"]["validation_evidence"][0]["exit_code"] == 7


def test_agent_provider_registry_resolves_configured_capability_and_fails_closed_unknown():
    bridge = _module("tools.node_architect.agent_provider_bridge")
    dispatcher = _module("tools.node_architect.semantic_dispatcher")
    provider = RecordingProvider()
    registry = bridge.ProviderRegistry({"configured-agent": provider})
    configured = _binding(
        registry=registry,
        provider_name="configured-agent",
        runner=RecordingValidationRunner(),
    )
    ok = dispatcher.dispatch_semantic_node(
        _node(), _source(), _semantic_input(), bindings={configured.node_id: configured}
    )
    assert ok["result"]["runtime_disposition"] == "CONTINUE"
    assert ok["result"]["provider_resolution"] == "CONFIGURED_REGISTRY"

    missing = _binding(
        registry=registry,
        provider_name="missing-agent",
        runner=RecordingValidationRunner(),
    )
    blocked = dispatcher.dispatch_semantic_node(
        _node(), _source(), _semantic_input(), bindings={missing.node_id: missing}
    )
    assert blocked["result"]["runtime_disposition"] == "BLOCK"
    assert blocked["result"]["reason_code"] == "AGENT_PROVIDER_UNAVAILABLE"


def test_fake_provider_is_explicitly_ineligible_for_live_closure():
    bridge = _module("tools.node_architect.agent_provider_bridge")
    dispatcher = _module("tools.node_architect.semantic_dispatcher")
    registry = bridge.ProviderRegistry({"fake": DeterministicFakeProvider()})
    binding = _binding(
        registry=registry,
        provider_name="fake",
        runner=RecordingValidationRunner(),
    )

    result = dispatcher.dispatch_semantic_node(
        _node(), _source(), _semantic_input(), bindings={binding.node_id: binding}
    )

    assert result["result"]["provider_evidence_class"] == "SYNTHETIC_TEST_ONLY"
    assert result["result"]["live_closure_eligible"] is False


def test_agent_provider_failure_blocks_lifecycle_before_readback(tmp_path: Path):
    lifecycle = _module("tools.node_architect.semantic_lifecycle")
    provider = RecordingProvider(unavailable=True)
    binding = _binding(provider=provider, runner=RecordingValidationRunner())
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
        "input_payload": _semantic_input(),
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
