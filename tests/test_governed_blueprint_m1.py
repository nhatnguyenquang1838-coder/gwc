"""M1: W3 blueprint — implementation_plan_ref required + real producer.

Fixes the W1-W7 review BLOCKER B7: GovernedExecutionBlueprint allowed
``implementation_plan_ref=None`` while the canonical RuntimePlan (M0)
requires a non-empty ``runtime_plan_ref``. M1 makes the field mandatory and
adds a real producer that reads the live Node Architect registries
(profile-registry, flow-policy-activation, node-registry, runbooks) so the
blueprint is compiled from canonical repo sources, not hand-assembled.
"""

from __future__ import annotations

import json

import pytest

from tools.node_architect.governed_execution_blueprint import (
    BlueprintValidationError,
    GovernedExecutionBlueprint,
    produce_governed_blueprint,
)


def _blueprint_payload() -> dict:
    return {
        "blueprint_id": "blueprint.scrum-672",
        "task_id": "SCRUM-672",
        "scenario": "standard_pr_delivery",
        "source_bindings": {
            "gwc_sha": "0e752b04c9f40a04fe402a4f25fcb12c8b9b4d72",
            "flow_ref": "core/node-architect/profile-registry.json",
            "flow_revision": "workflow-contract-v2-scrum392-policy-reconcile-20260811-r2",
            "flow_digest": "sha256:" + "1" * 64,
            "policy_ref": "core/node-architect/gate-applicability-policy-registry.json",
            "policy_revision": "policy-contract-v2-20260811-r1",
            "policy_digest": "sha256:" + "2" * 64,
            "project_profile_ref": "projects/gwc/project-profile.yaml",
        },
        "runbooks": [
            {"runbook_id": "standard-pr-delivery", "revision": "1.0.0", "digest": "sha256:" + "3" * 64}
        ],
        "nodes": [
            {
                "action": "validate",
                "node_id": "validation_quality.validator-execution",
                "node_instruction_ref": "core/node-architect/node-instructions/validation_quality/validator-execution.node-instruction.yaml",
                "node_instruction_digest": "sha256:" + "4" * 64,
                "implementation_ref": "tools/node_architect/validator_execution.py",
                "route_profile_revision": "route-v1",
                "graph_revision": "graph-v1",
                "node_registry_revision": "nodes-v1",
            }
        ],
        "topology": [
            {"action": "validate", "node_id": "validation_quality.validator-execution", "edges": []}
        ],
        "authority_requirements": [
            {"action": "validate", "gate": "G3_PR", "required": True}
        ],
        "implementation_plan_ref": "implementation-plan/SCRUM-672/r1",
    }


def test_blueprint_requires_implementation_plan_ref():
    """BLOCKER B7: implementation_plan_ref must be non-empty (W4 needs it)."""
    payload = _blueprint_payload()
    payload.pop("implementation_plan_ref")
    with pytest.raises(BlueprintValidationError, match="implementation_plan_ref"):
        GovernedExecutionBlueprint.from_dict(payload)


def test_blueprint_rejects_empty_implementation_plan_ref():
    payload = _blueprint_payload()
    payload["implementation_plan_ref"] = ""
    with pytest.raises(BlueprintValidationError, match="implementation_plan_ref"):
        GovernedExecutionBlueprint.from_dict(payload)


def test_blueprint_rejects_none_implementation_plan_ref():
    payload = _blueprint_payload()
    payload["implementation_plan_ref"] = None
    with pytest.raises(BlueprintValidationError, match="implementation_plan_ref"):
        GovernedExecutionBlueprint.from_dict(payload)


def test_producer_reads_live_registries():
    """Real producer: builds a blueprint from canonical repo registries."""
    blueprint = produce_governed_blueprint(
        task_id="SCRUM-668",
        scenario="standard_real_run",
        repo_root=".",
    )
    assert isinstance(blueprint, GovernedExecutionBlueprint)
    assert blueprint.task_id == "SCRUM-668"
    assert blueprint.scenario == "standard_real_run"
    assert blueprint.implementation_plan_ref
    assert blueprint.implementation_plan_ref.startswith("implementation-plan/")
    # source_bindings carry live gwc SHA + flow/policy digest from registries
    assert len(blueprint.source_bindings.get("gwc_sha", "")) == 40
    assert blueprint.source_bindings["flow_digest"].startswith("sha256:")
    assert blueprint.source_bindings["policy_digest"].startswith("sha256:")
    # runbooks from live runbook registry (at least one)
    assert len(blueprint.runbooks) >= 1
    assert all(rb.digest.startswith("sha256:") for rb in blueprint.runbooks)
    # nodes + topology from live node/graph registries
    assert len(blueprint.nodes) >= 1
    assert len(blueprint.topology) >= 1
    # never grants authority
    assert blueprint.authority_granted is False


def test_producer_blueprint_is_deterministic():
    first = produce_governed_blueprint(task_id="SCRUM-668", scenario="standard_real_run", repo_root=".")
    second = produce_governed_blueprint(task_id="SCRUM-668", scenario="standard_real_run", repo_root=".")
    assert first.blueprint_digest == second.blueprint_digest
    assert first.to_dict() == second.to_dict()


def test_producer_blueprint_survives_roundtrip():
    blueprint = produce_governed_blueprint(task_id="SCRUM-668", scenario="standard_real_run", repo_root=".")
    restored = GovernedExecutionBlueprint.from_dict(blueprint.to_dict())
    assert restored.blueprint_digest == blueprint.blueprint_digest
    assert restored.implementation_plan_ref == blueprint.implementation_plan_ref


def test_producer_preserves_multi_target_topology():
    """seq=13 M1: a source with >=2 outgoing route rows must preserve
    all route semantics deterministically in topology.edges, not collapse."""
    blueprint = produce_governed_blueprint(
        task_id="SCRUM-668",
        scenario="standard_real_run",
        repo_root=".",
    )
    # Verify every topology entry has an edges sequence.
    for entry in blueprint.topology:
        assert "edges" in entry, \
            f"topology entry missing 'edges' for {entry['action']}"
        assert isinstance(entry["edges"], tuple), \
            f"topology.edges must be tuple, got {type(entry['edges'])} for {entry['action']}"
    # Verify at least one source preserves multi-route.
    multi_route_entries = [e for e in blueprint.topology if len(e["edges"]) >= 2]
    assert len(multi_route_entries) >= 1, \
        "expected at least one source with >=2 preserved route rows"
    # Verify round-trip preserves all route semantics.
    restored = GovernedExecutionBlueprint.from_dict(blueprint.to_dict())
    for orig, rest in zip(blueprint.topology, restored.topology):
        assert orig["edges"] == rest["edges"], \
            f"route semantics not preserved in round-trip: {orig['edges']} != {rest['edges']}"


def test_producer_fails_closed_when_compiled_route_semantics_missing():
    """seq=14 M1: compiled Flow route table is canonical. When the compiled
    profile is absent, the producer MUST fail closed — it must NOT fall back
    to inventing continue/human_required semantics from the raw runtime graph."""
    import pathlib

    real_exists = pathlib.Path.exists

    def _fake_exists(self):
        if str(self).endswith("core/node-architect/flow-policy-compiled-profile.json"):
            return False
        return real_exists(self)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(pathlib.Path, "exists", _fake_exists)
    try:
        with pytest.raises(BlueprintValidationError, match="compiled route semantics"):
            produce_governed_blueprint(
                task_id="SCRUM-668",
                scenario="standard_real_run",
                repo_root=".",
            )
    finally:
        monkeypatch.undo()


def test_producer_topology_entries_and_edge_mappings_deep_frozen():
    """seq=14 M1: outer tuple immutability is insufficient — nested topology
    entries and their edge mappings must be deep-frozen after construction
    (no post-validation mutation of route semantics)."""
    import types

    blueprint = produce_governed_blueprint(
        task_id="SCRUM-668",
        scenario="standard_real_run",
        repo_root=".",
    )
    entry = blueprint.topology[0]
    # Nested topology entry itself must be immutable.
    assert isinstance(entry, types.MappingProxyType), \
        f"topology entry must be a mapping proxy, got {type(entry)}"
    with pytest.raises(TypeError):
        entry["action"] = "mutated"
    with pytest.raises(TypeError):
        entry["terminal"] = True
    # Edge mappings inside the entry must be deep-frozen too.
    edges = entry["edges"]
    assert isinstance(edges, tuple)
    if edges:
        edge0 = edges[0]
        assert isinstance(edge0, types.MappingProxyType), \
            f"edge mapping must be a mapping proxy, got {type(edge0)}"
        with pytest.raises(TypeError):
            edge0["target"] = "mutated"
        with pytest.raises(TypeError):
            edge0["condition_id"] = "mutated"
