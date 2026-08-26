from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path


def _module(name: str):
    spec = importlib.util.find_spec(name)
    assert spec is not None, f"{name} must exist"
    return importlib.import_module(name)


def _activation(**overrides) -> dict:
    value = {
        "schema_version": "1.0",
        "artifact_type": "shadow-runtime-activation",
        "enabled": True,
        "kill_switch_engaged": False,
        "mode": "shadow_readonly",
        "authority": "none",
        "output_effect": "observe_only",
        "decision_authority": False,
        "automatic_gate_advance": False,
        "fail_closed": True,
        "exact_revision_binding": True,
        "canonical_population": "canonical_81",
        "route_source": "tools/node_architect/canonical_shadow_route.py",
        "adapter_source": "tools/node_architect/shadow_adapters.py",
        "registry_source": "core/node-architect/node-registry.json",
    }
    value.update(overrides)
    return value


def _event(**overrides) -> dict:
    value = {
        "task_id": "SCRUM-566",
        "run_id": "w8-run",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "branch": "chatgpt/scrum-566-agent-runtime-corrective",
        "base_sha": "a" * 40,
        "exact_revision": "b" * 40,
        "scope_hash": "sha256:" + "c" * 64,
        "gate": "G2_EXECUTION",
        "requested_action": "repair_ci",
        "scenario": "ci_failure",
        "profile_revision": "profile-1",
        "graph_revision": "graph-1",
        "node_registry_revision": "registry-1",
        "policy_revision": "policy-1",
        "input_payload": {"ci": "failed"},
    }
    value.update(overrides)
    return value


def _observed(**overrides) -> dict:
    value = {
        "repository": "nhatnguyenquang1838-coder/gwc",
        "branch": "chatgpt/scrum-566-agent-runtime-corrective",
        "base_sha": "a" * 40,
        "head_sha": "b" * 40,
        "profile_revision": "profile-1",
        "graph_revision": "graph-1",
        "node_registry_revision": "registry-1",
        "policy_revision": "policy-1",
    }
    value.update(overrides)
    return value


def _profile(**overrides) -> dict:
    value = {
        "profile_id": "w8-profile",
        "revision": "profile-1",
        "bound_graph_revision": "graph-1",
        "bound_node_registry_revision": "registry-1",
        "policy_revision": "policy-1",
    }
    value.update(overrides)
    return value


def _graph(**overrides) -> dict:
    value = {"revision": {"revision_id": "graph-1"}, "edges": []}
    value.update(overrides)
    return value


def _node(node_id: str = "repo_delivery.ci-failure-repair", **overrides) -> dict:
    value = {
        "id": node_id,
        "version": "1.0.0",
        "family": "repo_delivery",
        "effect_class": "read_only",
        "runtime_executable": True,
        "runtime_guard": {
            "gates": ["G2_EXECUTION"],
            "actions": ["repair_ci"],
            "scenarios": ["ci_failure"],
        },
    }
    value.update(overrides)
    return value


def _registry(nodes=None, **overrides) -> dict:
    value = {
        "revision": {"revision_id": "registry-1"},
        "nodes": list(nodes if nodes is not None else [_node()]),
    }
    value.update(overrides)
    return value


def _semantic_source(node, *, root):
    return {
        "status": "NAMED_TOOL_PRESENT",
        "runtime_eligible": True,
        "reason_code": "SEMANTIC_NAMED_TOOL_BOUND",
        "evaluator_path": f"tools/node_architect/{node['id'].split('.', 1)[-1].replace('-', '_')}.py",
        "descriptor_path": None,
    }


def _resolve(**overrides):
    resolver = _module("tools.node_architect.canonical_shadow_route")
    kwargs = {
        "event": _event(),
        "registry": _registry(),
        "activation": _activation(),
        "observed_state": _observed(),
        "profile": _profile(),
        "graph_registry": _graph(),
        "root": Path("."),
        "source_resolver": _semantic_source,
    }
    kwargs.update(overrides)
    return resolver.resolve_shadow_route(**kwargs)


def test_full_activation_schema_is_enforced_before_route_selection():
    out = _resolve(activation=_activation(output_effect=None))
    assert out["status"] == "SHADOW_DISABLED_FAIL_CLOSED"
    assert out["reason_code"] == "SHADOW_ACTIVATION_SCHEMA_INVALID"
    assert out["selected_node_ids"] == []


def test_exact_runtime_identity_is_bound_before_node_selection():
    for field, value in (
        ("repository", "other/repo"),
        ("branch", "other-branch"),
        ("base_sha", "d" * 40),
        ("head_sha", "e" * 40),
        ("profile_revision", "profile-2"),
        ("graph_revision", "graph-2"),
        ("node_registry_revision", "registry-2"),
        ("policy_revision", "policy-2"),
    ):
        out = _resolve(observed_state=_observed(**{field: value}))
        assert out["status"] == "SHADOW_DISABLED_FAIL_CLOSED", field
        assert out["reason_code"] == "SHADOW_RUNTIME_IDENTITY_DRIFT", field
        assert out["selected_node_ids"] == [], field


def test_profile_graph_registry_bindings_are_validated():
    out = _resolve(profile=_profile(bound_graph_revision="graph-stale"))
    assert out["status"] == "SHADOW_DISABLED_FAIL_CLOSED"
    assert out["reason_code"] == "SHADOW_GRAPH_REVISION_DRIFT"

    out = _resolve(profile=_profile(bound_node_registry_revision="registry-stale"))
    assert out["status"] == "SHADOW_DISABLED_FAIL_CLOSED"
    assert out["reason_code"] == "SHADOW_NODE_REGISTRY_REVISION_DRIFT"


def test_runtime_executable_false_never_becomes_shadow_invocation():
    out = _resolve(registry=_registry([_node(runtime_executable=False)]))
    assert out["status"] == "SHADOW_NO_APPLICABLE_NODES"
    assert out["reason_code"] == "SHADOW_NO_APPLICABLE_NODES"
    assert out["selected_node_ids"] == []
    assert out["rejections"][0]["reason_code"] == "NODE_NOT_RUNTIME_EXECUTABLE"


def test_node_specific_guard_overrides_family_match():
    node = _node(runtime_guard={"gates": ["G3_PR"], "actions": ["repair_ci"], "scenarios": ["ci_failure"]})
    out = _resolve(registry=_registry([node]))
    assert out["status"] == "SHADOW_NO_APPLICABLE_NODES"
    assert out["selected_node_ids"] == []
    assert out["rejections"][0]["reason_code"] == "SHADOW_NODE_GUARD_REJECTED"


def test_semantic_source_missing_blocks_family_candidate():
    out = _resolve(
        source_resolver=lambda node, *, root: {
            "status": "DESCRIPTOR_ONLY",
            "runtime_eligible": False,
            "reason_code": "SEMANTIC_EVALUATOR_MISSING",
            "evaluator_path": None,
        }
    )
    assert out["status"] == "SHADOW_NO_APPLICABLE_NODES"
    assert out["rejections"][0]["reason_code"] == "SEMANTIC_EVALUATOR_MISSING"


def test_unknown_and_ambiguous_scenarios_are_typed_fail_closed():
    out = _resolve(event=_event(scenario="not-mapped"))
    assert out["status"] == "SHADOW_NO_APPLICABLE_ROUTE"
    assert out["reason_code"] == "SHADOW_SCENARIO_UNMAPPED"

    route_packs = {
        "R1": {"scenario": "ci_failure", "families": ["repo_delivery"], "runtime_executable": True},
        "R2": {"scenario": "ci_failure", "families": ["repo_delivery"], "runtime_executable": True},
    }
    out = _resolve(route_packs=route_packs)
    assert out["status"] == "SHADOW_DISABLED_FAIL_CLOSED"
    assert out["reason_code"] == "SHADOW_ROUTE_AMBIGUOUS"


def test_valid_decision_carries_revision_provenance_and_never_authority():
    out = _resolve()
    assert out["status"] == "SHADOW_ROUTE_RESOLVED"
    assert out["route_pack"] == "RP-03"
    assert out["selected_node_ids"] == ["repo_delivery.ci-failure-repair"]
    assert out["profile_revision"] == "profile-1"
    assert out["graph_revision"] == "graph-1"
    assert out["node_registry_revision"] == "registry-1"
    assert out["policy_revision"] == "policy-1"
    assert out["authority_granted"] is False
    assert out["decision_authority"] is False


def test_shadow_orchestrator_consumes_canonical_route_decision_not_family_selector():
    orchestrator = _module("tools.node_architect.shadow_orchestrator")
    calls = []

    def canonical_resolver(**kwargs):
        calls.append(kwargs)
        return {
            "status": "SHADOW_ROUTE_RESOLVED",
            "reason_code": "SHADOW_ROUTE_RESOLVED",
            "route_pack": "RP-03",
            "selected_node_ids": ["repo_delivery.ci-failure-repair"],
            "rejections": [],
            "authority_granted": False,
            "decision_authority": False,
            "profile_revision": "profile-1",
            "graph_revision": "graph-1",
            "node_registry_revision": "registry-1",
            "policy_revision": "policy-1",
        }

    out = orchestrator.run_shadow_event(
        _event(),
        _registry(),
        _activation(),
        observed_revision="b" * 40,
        observed_state=_observed(),
        profile=_profile(),
        graph_registry=_graph(),
        route_resolver=canonical_resolver,
        source_resolver=_semantic_source,
    )

    assert len(calls) == 1
    assert out["route_pack"] == "RP-03"
    assert out["selected_node_count"] == 1
    assert out["results"][0]["node_id"] == "repo_delivery.ci-failure-repair"
    assert out["decision_authority"] is False


def test_known_route_with_zero_nodes_does_not_report_shadow_executed():
    orchestrator = _module("tools.node_architect.shadow_orchestrator")

    def no_nodes(**kwargs):
        return {
            "status": "SHADOW_NO_APPLICABLE_NODES",
            "reason_code": "SHADOW_NO_APPLICABLE_NODES",
            "route_pack": "RP-03",
            "selected_node_ids": [],
            "rejections": [],
            "authority_granted": False,
            "decision_authority": False,
        }

    out = orchestrator.run_shadow_event(
        _event(),
        _registry([]),
        _activation(),
        observed_revision="b" * 40,
        observed_state=_observed(),
        profile=_profile(),
        graph_registry=_graph(),
        route_resolver=no_nodes,
        source_resolver=_semantic_source,
    )
    assert out["status"] == "SHADOW_NO_APPLICABLE_NODES"
    assert out["results"] == []
