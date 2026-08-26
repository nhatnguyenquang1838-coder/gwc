from __future__ import annotations

import importlib
import importlib.util
import json
from pathlib import Path

from tools.node_architect.ai_agent_adapter import execute
from tools.node_architect.build_node_instruction_pack import build_node_instruction_pack
from tools.node_architect.shadow_adapters import execute_shadow_node


SAFE_PATH = "tools/node_architect/scratch/foo.py"


def _request() -> dict:
    return {
        "schema_version": "1.0",
        "run_id": "scrum-566-red-1",
        "task_id": "SCRUM-566",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "preprod_base_sha": "f" * 40,
        "working_branch": "chatgpt/scrum-566-agent-runtime-corrective",
        "scope_hash": "sha256:" + "a" * 64,
        "graph_revision": "graph-1",
        "policy_revision": "policy-1",
        "allowed_paths": [SAFE_PATH],
        "prohibited_paths": [],
        "authorized_actions": ["modify_approved_files"],
        "validation_commands": ["python -m pytest tests/scratch"],
        "idempotency_key": "scrum-566-idem-1",
    }


def test_instruction_digest_binds_meaning_bearing_semantics():
    request = _request()
    pack_a = build_node_instruction_pack(
        request,
        g0_g1_decision_ref="decision-A",
        objective="Objective A",
        acceptance_criteria=["AC-A"],
        gate_node_route=["G2:node-A"],
        plan_refs=["plan-A"],
    )
    pack_b = build_node_instruction_pack(
        request,
        g0_g1_decision_ref="decision-B",
        objective="Objective B",
        acceptance_criteria=["AC-B"],
        gate_node_route=["G2:node-B"],
        plan_refs=["plan-B"],
    )
    assert pack_a.content_digest != pack_b.content_digest


class MissingValidationProvider:
    name = "missing-validation-provider"

    def run(self, pack):
        return {
            "changed_paths": [SAFE_PATH],
            "recorded_actions": ["modify_approved_files"],
        }


def test_missing_validation_evidence_fails_closed():
    result = execute(_request(), provider=MissingValidationProvider(), idempotency_store={})
    assert result["terminal_outcome"] == "FAIL_CLOSED"
    assert any("validation" in finding for finding in result["findings"])


def _event() -> dict:
    return {
        "task_id": "SCRUM-566",
        "run_id": "semantic-runtime-red",
        "gate": "G2_EXECUTION",
        "exact_revision": "f" * 40,
    }


def test_runtime_executable_false_blocks_shadow_execution():
    node = {
        "id": "repo-delivery.example",
        "version": "1.0",
        "family": "repo_delivery",
        "effect_class": "read_only",
        "runtime_executable": False,
    }
    result = execute_shadow_node(node, _event(), {})
    assert result["applicability"] == "BLOCKED"
    assert result["reason_code"] == "NODE_NOT_RUNTIME_EXECUTABLE"


def test_descriptor_only_node_cannot_claim_semantic_execution():
    node = {
        "id": "repo-delivery.descriptor-only",
        "version": "1.0",
        "family": "repo_delivery",
        "effect_class": "read_only",
        "runtime_executable": True,
        "source_resolution": {"kind": "DESCRIPTOR_ONLY"},
    }
    result = execute_shadow_node(node, _event(), {})
    assert result["applicability"] == "BLOCKED"
    assert result["reason_code"] == "SEMANTIC_EVALUATOR_MISSING"


def _semantic_resolver():
    spec = importlib.util.find_spec("tools.node_architect.semantic_source_resolver")
    assert spec is not None, "canonical semantic source resolver must exist"
    return importlib.import_module("tools.node_architect.semantic_source_resolver").resolve_semantic_source


def _write(path: Path, text: str = "# evaluator\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_semantic_resolver_prefers_descriptor_evaluator_over_named_tool(tmp_path: Path):
    descriptor = tmp_path / "core/node-catalog/example.node.json"
    declared = "tools/node_architect/custom_evaluator.py"
    _write(tmp_path / declared)
    _write(tmp_path / "tools/node_architect/example_node.py")
    _write(
        descriptor,
        json.dumps({"source_resolution": {"evaluator": declared}}),
    )
    node = {
        "id": "repo_delivery.example-node",
        "runtime_executable": True,
        "provenance": {"source_path": "core/node-catalog/example.node.json"},
    }

    result = _semantic_resolver()(node, root=tmp_path)

    assert result["status"] == "SOURCE_RESOLVED_EVALUATOR"
    assert result["evaluator_path"] == declared
    assert result["runtime_eligible"] is True


def test_semantic_resolver_uses_named_tool_fallback(tmp_path: Path):
    named = "tools/node_architect/timeout_recovery.py"
    _write(tmp_path / named)
    node = {
        "id": "failure_recovery.timeout-recovery",
        "runtime_executable": True,
        "provenance": {},
    }

    result = _semantic_resolver()(node, root=tmp_path)

    assert result["status"] == "NAMED_TOOL_PRESENT"
    assert result["evaluator_path"] == named
    assert result["runtime_eligible"] is True


def test_semantic_resolver_descriptor_only_is_typed_and_ineligible(tmp_path: Path):
    node = {
        "id": "package_export.export-manifest-generation",
        "runtime_executable": True,
        "provenance": {"source_path": "core/node-catalog/export.node.json"},
    }

    result = _semantic_resolver()(node, root=tmp_path)

    assert result["status"] == "DESCRIPTOR_ONLY"
    assert result["reason_code"] == "SEMANTIC_EVALUATOR_MISSING"
    assert result["runtime_eligible"] is False


def test_semantic_resolver_rejects_descriptor_path_escape(tmp_path: Path):
    descriptor = tmp_path / "core/node-catalog/escape.node.json"
    _write(
        descriptor,
        json.dumps({"source_resolution": {"evaluator": "../../outside.py"}}),
    )
    node = {
        "id": "repo_delivery.escape",
        "runtime_executable": True,
        "provenance": {"source_path": "core/node-catalog/escape.node.json"},
    }

    result = _semantic_resolver()(node, root=tmp_path)

    assert result["status"] == "INVALID_SOURCE_BINDING"
    assert result["reason_code"] == "SEMANTIC_EVALUATOR_PATH_UNSAFE"
    assert result["runtime_eligible"] is False


def test_semantic_resolver_runtime_disabled_is_ineligible(tmp_path: Path):
    _write(tmp_path / "tools/node_architect/timeout_recovery.py")
    node = {
        "id": "failure_recovery.timeout-recovery",
        "runtime_executable": False,
        "provenance": {},
    }

    result = _semantic_resolver()(node, root=tmp_path)

    assert result["status"] == "NOT_RUNTIME_EXECUTABLE"
    assert result["reason_code"] == "NODE_NOT_RUNTIME_EXECUTABLE"
    assert result["runtime_eligible"] is False
