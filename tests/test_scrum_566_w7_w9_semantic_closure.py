from __future__ import annotations

import copy
import importlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _module(name: str):
    spec = importlib.util.find_spec(name)
    assert spec is not None, f"{name} must exist"
    return importlib.import_module(name)


def _load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_corrected_semantic_executability_ladder_is_e0_through_e6():
    module = _module("tools.node_architect.semantic_executability")
    assert module.E_LEVELS == (
        "E0_CATALOGUED",
        "E1_INSTRUCTION_READY",
        "E2_SEMANTIC_IMPLEMENTATION_BOUND",
        "E3_CANONICAL_ROUTE_BOUND",
        "E4_SEMANTIC_REPLAY_PROVEN",
        "E5_LIVE_AGENT_OBSERVED",
        "E6_AUTHORIZED_AGENT_EXECUTION_PROVEN",
    )


def test_historical_envelope_replay_never_promotes_semantic_level():
    module = _module("tools.node_architect.semantic_executability")
    record = module.qualify_semantic_node(
        node_id="repo_delivery.example",
        instruction_ready=True,
        implementation_binding=None,
        canonical_route_bound=True,
        replay_evidence={
            "replay_proven": True,
            "evidence_class": "HISTORICAL_ENVELOPE_COMPATIBILITY",
            "semantic_execution": False,
        },
        live_evidence=None,
        authorized_evidence=None,
    )
    assert record["executability_level"] == "E1_INSTRUCTION_READY"
    assert record["shadow_envelope_enabled"] is True
    assert record["semantic_implementation_bound"] is False
    assert record["semantic_replay_proven"] is False


def test_descriptor_only_81_without_instruction_or_evaluator_cannot_semantically_close(tmp_path: Path):
    compiler = _module("tools.node_architect.semantic_implementation_registry")
    registry = {
        "declared_slot_count": 81,
        "revision": "synthetic-r1",
        "nodes": [
            {
                "id": f"repo_delivery.node-{index:02d}",
                "family": "repo_delivery",
                "version": "1.0.0",
                "effect_class": "read_only",
                "provenance": {"source_path": f"missing/{index}.json"},
            }
            for index in range(81)
        ],
    }
    report = compiler.compile_semantic_implementation_registry(registry, root=tmp_path)
    assert report["status"] == "FAIL"
    assert report["summary"]["implementation_bound_count"] == 0
    assert "SEMANTIC_IMPLEMENTATION_COVERAGE_GAP" in report["errors"]


def test_actual_canonical_81_compile_to_exact_valid_semantic_bindings():
    compiler = _module("tools.node_architect.semantic_implementation_registry")
    registry = _load("core/node-architect/node-registry.json")
    report = compiler.compile_semantic_implementation_registry(registry, root=ROOT)
    assert report["status"] == "PASS", report["errors"][:10]
    assert report["summary"]["canonical_node_count"] == 81
    assert report["summary"]["implementation_bound_count"] == 81
    assert len(report["bindings"]) == 81
    assert len({item["node_id"] for item in report["bindings"]}) == 81
    assert all(item["instruction_valid"] for item in report["bindings"])
    assert all(item["implementation_callable_valid"] for item in report["bindings"])
    assert all(item["readback_contract"] for item in report["bindings"])
    assert all(item["next_route_contract"] for item in report["bindings"])
    assert all(item["side_effect_class"] for item in report["bindings"])
    assert all(item["authority_requirements"] for item in report["bindings"])


def test_binding_is_exact_node_version_and_registry_revision_aware():
    compiler = _module("tools.node_architect.semantic_implementation_registry")
    registry = _load("core/node-architect/node-registry.json")
    report = compiler.compile_semantic_implementation_registry(registry, root=ROOT)
    binding = report["bindings"][0]
    assert binding["node_version"]
    assert binding["node_registry_revision"] == compiler.node_registry_revision(registry)
    assert binding["binding_digest"].startswith("sha256:")

    stale = copy.deepcopy(registry)
    stale["nodes"][0]["version"] = str(stale["nodes"][0]["version"]) + "-stale"
    errors = compiler.validate_semantic_implementation_registry(report, node_registry=stale, root=ROOT)
    assert "SEMANTIC_BINDING_NODE_VERSION_DRIFT" in errors


def test_duplicate_node_ids_and_slot_82_never_satisfy_semantic_baseline():
    compiler = _module("tools.node_architect.semantic_implementation_registry")
    registry = _load("core/node-architect/node-registry.json")

    duplicate = copy.deepcopy(registry)
    duplicate["nodes"][1]["id"] = duplicate["nodes"][0]["id"]
    out = compiler.compile_semantic_implementation_registry(duplicate, root=ROOT)
    assert out["status"] == "FAIL"
    assert "CANONICAL_NODE_ID_DUPLICATE" in out["errors"]

    slot82 = copy.deepcopy(registry)
    slot82["nodes"].append(copy.deepcopy(slot82["nodes"][0]))
    slot82["nodes"][-1]["id"] = "repo_delivery.slot-82-must-not-count"
    slot82["declared_slot_count"] = 82
    out = compiler.compile_semantic_implementation_registry(slot82, root=ROOT)
    assert out["status"] == "FAIL"
    assert "CANONICAL_NODE_COUNT_MISMATCH" in out["errors"]


def test_descriptor_without_specific_code_uses_instruction_semantics_not_shadow_adapter():
    compiler = _module("tools.node_architect.semantic_implementation_registry")
    registry = _load("core/node-architect/node-registry.json")
    report = compiler.compile_semantic_implementation_registry(registry, root=ROOT)
    fallbacks = [item for item in report["bindings"] if item["implementation_kind"] == "instruction_contract"]
    assert fallbacks, "the corrective lane must materialize former descriptor-only nodes"
    assert all(
        item["implementation_ref"]
        == "tools/node_architect/instruction_contract_evaluator.py:evaluate_instruction_contract"
        for item in fallbacks
    )
    assert all(item["semantic_source_kind"] == "NODE_INSTRUCTION_CONTRACT" for item in fallbacks)
    assert all("shadow_adapters.py" not in item["implementation_ref"] for item in fallbacks)


def test_concrete_implementation_invocation_identity_is_recorded():
    compiler = _module("tools.node_architect.semantic_implementation_registry")
    runtime = _module("tools.node_architect.semantic_implementation_runtime")
    registry = _load("core/node-architect/node-registry.json")
    compiled = compiler.compile_semantic_implementation_registry(registry, root=ROOT)
    binding = next(item for item in compiled["bindings"] if item["implementation_kind"] == "instruction_contract")
    result = runtime.invoke_semantic_implementation(
        binding,
        {
            "task_id": "SCRUM-566",
            "run_id": "w9-runtime",
            "gate": binding["gates"][0],
            "exact_revision": "a" * 40,
            "input_payload": {
                key: {"present": True} for key in binding["entry_contract"]
            },
        },
        root=ROOT,
    )
    assert result["implementation_invoked"] is True
    assert result["node_id"] == binding["node_id"]
    assert result["implementation_ref"] == binding["implementation_ref"]
    assert result["binding_digest"] == binding["binding_digest"]
    assert result["invocation_digest"].startswith("sha256:")
    assert result["authority_granted"] is False


def test_semantic_qualification_requires_real_invocation_digest_for_e4():
    module = _module("tools.node_architect.semantic_executability")
    binding = {"binding_digest": "sha256:" + "1" * 64, "implementation_ref": "x:y"}
    no_invocation = module.qualify_semantic_node(
        node_id="x.y",
        instruction_ready=True,
        implementation_binding=binding,
        canonical_route_bound=True,
        replay_evidence={"semantic_execution": True, "implementation_invoked": True},
        live_evidence=None,
        authorized_evidence=None,
    )
    assert no_invocation["executability_level"] == "E3_CANONICAL_ROUTE_BOUND"

    invoked = module.qualify_semantic_node(
        node_id="x.y",
        instruction_ready=True,
        implementation_binding=binding,
        canonical_route_bound=True,
        replay_evidence={
            "semantic_execution": True,
            "implementation_invoked": True,
            "invocation_digest": "sha256:" + "2" * 64,
            "binding_digest": binding["binding_digest"],
        },
        live_evidence=None,
        authorized_evidence=None,
    )
    assert invoked["executability_level"] == "E4_SEMANTIC_REPLAY_PROVEN"
    assert invoked["semantic_replay_proven"] is True
