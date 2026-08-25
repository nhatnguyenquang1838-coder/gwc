import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.node_architect.shadow_adapters import build_adapter_registry, execute_shadow_node


def node(effect="read_only", suspend=False):
    return {
        "id": "repo_delivery.example",
        "family": "repo_delivery",
        "version": "1.0.0",
        "maturity": "experimental",
        "effect_class": effect,
        "authority_class": "human_required",
        "suspension": {"suspendable": suspend, "resume_metadata": ["task", "revision"]},
    }


def event():
    return {"task_id": "SCRUM-X", "run_id": "run-1", "gate": "G2_EXECUTION", "exact_revision": "abc123"}


def test_build_adapter_registry_binds_every_node():
    reg = {"nodes": [node(), {**node(), "id": "gate_authority.other"}]}
    adapters = build_adapter_registry(reg)
    assert set(adapters) == {"repo_delivery.example", "gate_authority.other"}
    assert all(not adapter["write_capable"] for adapter in adapters.values())


def test_read_only_node_executes_without_effects():
    result = execute_shadow_node(node(), event(), {"k": "v"})
    assert result["applicability"] == "APPLICABLE"
    assert result["executed_effects"] == []
    assert result["proposed_effects"] == []
    assert result["authority_granted"] is False


def test_write_class_node_is_proposal_only():
    result = execute_shadow_node(node("external_write"), event(), {"target": "repo"})
    assert result["outcome"] == "WOULD_REQUEST_ACTION"
    assert result["executed_effects"] == []
    assert result["proposed_effects"][0]["effect_class"] == "external_write"


def test_suspendable_node_returns_checkpoint_recommendation():
    result = execute_shadow_node(node(suspend=True), event(), {})
    assert result["checkpoint"]["recommended"] is True
    assert result["checkpoint"]["resume_metadata"] == ["task", "revision"]


def test_result_digest_is_deterministic():
    a = execute_shadow_node(node(), event(), {"a": 1})
    b = execute_shadow_node(node(), event(), {"a": 1})
    assert a["result_digest"] == b["result_digest"]


def test_repository_registry_binds_exactly_81_baseline_adapters():
    registry = json.loads((ROOT / "core/node-architect/node-registry.json").read_text(encoding="utf-8"))
    adapters = build_adapter_registry(registry)
    assert len(adapters) == 81
    assert len(set(adapters)) == 81
    assert all(adapter["mode"] == "shadow_readonly" for adapter in adapters.values())
    assert all(adapter["authority"] == "none" for adapter in adapters.values())
    assert all(adapter["write_capable"] is False for adapter in adapters.values())
