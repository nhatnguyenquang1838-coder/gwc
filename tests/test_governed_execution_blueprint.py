from __future__ import annotations

import copy

import pytest

from tools.node_architect.governed_execution_blueprint import (
    BlueprintValidationError,
    BlueprintNodeBinding,
    GovernedExecutionBlueprint,
    RunbookBinding,
)


def _blueprint() -> GovernedExecutionBlueprint:
    return GovernedExecutionBlueprint(
        blueprint_id="blueprint.scrum-672",
        task_id="SCRUM-672",
        scenario="standard_pr_delivery",
        source_bindings={
            "gwc_sha": "0e752b04c9f40a04fe402a4f25fcb12c8b9b4d72",
            "flow_ref": "core/node-architect/profile-registry.json",
            "flow_revision": "workflow-contract-v2-scrum392-policy-reconcile-20260811-r2",
            "flow_digest": "sha256:" + "1" * 64,
            "policy_ref": "core/node-architect/gate-applicability-policy-registry.json",
            "policy_revision": "policy-contract-v2-20260811-r1",
            "policy_digest": "sha256:" + "2" * 64,
            "project_profile_ref": "projects/gwc/project-profile.yaml",
        },
        runbooks=(
            RunbookBinding(
                runbook_id="standard-pr-delivery",
                revision="1.0.0",
                digest="sha256:" + "3" * 64,
            ),
        ),
        nodes=(
            BlueprintNodeBinding(
                action="validate",
                node_id="validation_quality.validator-execution",
                node_instruction_ref="core/node-architect/node-instructions/validation_quality/validator-execution.node-instruction.yaml",
                node_instruction_digest="sha256:" + "4" * 64,
                implementation_ref="tools/node_architect/validator_execution.py",
                route_profile_revision="route-v1",
                graph_revision="graph-v1",
                node_registry_revision="nodes-v1",
            ),
        ),
        topology=(
            {"action": "validate", "node_id": "validation_quality.validator-execution", "next": "terminal"},
        ),
        authority_requirements=(
            {"action": "validate", "gate": "G3_PR", "required": True},
        ),
        implementation_plan_ref="implementation-plan/SCRUM-672/r1",
    )


def test_blueprint_digest_is_deterministic_and_authority_is_declarative():
    first = _blueprint()
    second = GovernedExecutionBlueprint.from_dict(first.to_dict())

    assert first.blueprint_digest == second.blueprint_digest
    assert first.authority_granted is False
    assert "authority_granted" not in first.to_dict()


def test_blueprint_rejects_authority_grant_fields():
    payload = _blueprint().to_dict()
    payload["authority_granted"] = True

    with pytest.raises(BlueprintValidationError, match="authority_granted"):
        GovernedExecutionBlueprint.from_dict(payload)


def test_blueprint_rejects_missing_runbook_digest():
    payload = _blueprint().to_dict()
    payload["runbooks"][0].pop("digest")

    with pytest.raises(BlueprintValidationError, match="runbook"):
        GovernedExecutionBlueprint.from_dict(payload)


def test_blueprint_rejects_missing_node_instruction_binding():
    payload = _blueprint().to_dict()
    payload["nodes"][0]["node_instruction_ref"] = None

    with pytest.raises(BlueprintValidationError, match="node_instruction_ref"):
        GovernedExecutionBlueprint.from_dict(payload)


def test_blueprint_rejects_topology_action_without_node_binding():
    payload = _blueprint().to_dict()
    payload["topology"].append({"action": "missing", "node_id": "ghost.node", "next": "terminal"})

    with pytest.raises(BlueprintValidationError, match="topology"):
        GovernedExecutionBlueprint.from_dict(payload)


def test_blueprint_rejects_duplicate_or_ambiguous_actions():
    payload = _blueprint().to_dict()
    payload["topology"] = [
        payload["topology"][0],
        {"action": "validate", "node_id": "validation_quality.validator-execution", "next": "terminal"},
    ]

    with pytest.raises(BlueprintValidationError, match="ambiguous"):
        GovernedExecutionBlueprint.from_dict(payload)


def test_blueprint_rejects_material_source_digest_drift():
    blueprint = _blueprint()
    expected = dict(blueprint.source_bindings)
    expected["flow_digest"] = "sha256:" + "9" * 64
    expected["flow_revision"] = "stale"

    with pytest.raises(BlueprintValidationError, match="source"):
        blueprint.validate_source_bindings(expected)


def test_blueprint_is_immutable():
    blueprint = _blueprint()
    with pytest.raises(AttributeError):
        blueprint.scenario = "other"
    with pytest.raises(TypeError):
        blueprint.source_bindings["flow_ref"] = "other"


def test_runbook_binding_requires_sha256_digest():
    with pytest.raises(BlueprintValidationError, match="digest"):
        RunbookBinding("runbook", "1.0.0", "not-a-digest")
