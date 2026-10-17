"""SCRUM-809: exact G2 action vocabulary agreement; never grants authority."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tools.validate_gate_action import GATE_MINIMUM_ACTIONS
from tools.node_architect.authority_boundary_check import ACTION_TO_MINIMUM_GATE
from tools.node_architect.scope_hash_calculation import CANONICAL_ACTIONS

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas/g2-execution-envelope.schema.json").read_text())
CANONICAL_G2 = frozenset(GATE_MINIMUM_ACTIONS["G2_EXECUTION"])


def test_g2_schema_matches_canonical_gate_action_set_exactly():
    assert set(SCHEMA["properties"]["authorized_actions"]["items"]["enum"]) == CANONICAL_G2
    assert len(SCHEMA["properties"]["authorized_actions"]["items"]["enum"]) == len(CANONICAL_G2)


@pytest.mark.parametrize("action", sorted(CANONICAL_G2))
def test_every_g2_action_is_understood_by_every_authority_consumer(action):
    assert action in CANONICAL_ACTIONS
    assert ACTION_TO_MINIMUM_GATE[action] == "G2_EXECUTION"
    allowed = SCHEMA["properties"]["authorized_actions"]["items"]["enum"]
    assert Draft202012Validator({"type": "array", "items": {"enum": allowed}}).is_valid([action])


@pytest.mark.parametrize("action", [
    "create_working_branch", "add_files", "stage_commit_push",
    "open_or_update_draft_pr", "merge_approved_pr",
    "deploy_approved_release", "production_data_write",
    "force_push", "undefined_action"
])
def test_old_aliases_cross_gate_effects_and_unknown_values_fail_closed(action):
    allowed = SCHEMA["properties"]["authorized_actions"]["items"]["enum"]
    assert not Draft202012Validator({"type": "array", "items": {"enum": allowed}}).is_valid([action])


def test_authorized_and_excluded_are_distinct_contracts():
    assert not (CANONICAL_G2 & set(SCHEMA["properties"]["excluded_actions"]["items"]["enum"]))
    assert "open_or_update_draft_pr" not in CANONICAL_G2
    assert "merge_approved_pr" not in CANONICAL_G2


def test_v11_is_exact_current_contract_and_v10_is_historical_only():
    from tools.node_architect.g2_execution_envelope_render import _SCHEMA_VERSION
    historical = json.loads((ROOT / "schemas/historical/g2-execution-envelope-v1.0.schema.json").read_text())
    assert _SCHEMA_VERSION == "1.1"
    assert SCHEMA["properties"]["schema_version"] == {"const": "1.1"}
    assert historical["properties"]["schema_version"] == {"const": "1.0"}
    old_actions = set(historical["properties"]["authorized_actions"]["items"]["enum"])
    assert old_actions == {"create_working_branch", "add_files", "run_sandboxed_validation", "stage_commit_push"}
    assert set(SCHEMA["properties"]["authorized_actions"]["items"]["enum"]) == CANONICAL_G2


def test_legacy_envelope_requires_historical_schema_and_never_current_activation():
    historical = json.loads((ROOT / "schemas/historical/g2-execution-envelope-v1.0.schema.json").read_text())
    original = json.loads((ROOT / "schemas/g2-execution-envelope.schema.json").read_text())
    def minimal_versioned(schema, version, action):
        # Exact version/action validation is independent of envelope content validity.
        return {"schema_version": version, "authorized_actions": [action]}
    for name in ("create_working_branch", "add_files", "stage_commit_push"):
        old = minimal_versioned(historical, "1.0", name)
        assert Draft202012Validator({"properties": {
            "schema_version": historical["properties"]["schema_version"],
            "authorized_actions": historical["properties"]["authorized_actions"]
        }}).is_valid(old)
        assert not Draft202012Validator({"properties": {
            "schema_version": original["properties"]["schema_version"],
            "authorized_actions": original["properties"]["authorized_actions"]
        }}).is_valid(old)
    fresh = minimal_versioned(original, "1.1", "modify_approved_files")
    assert Draft202012Validator({"properties": {
        "schema_version": original["properties"]["schema_version"],
        "authorized_actions": original["properties"]["authorized_actions"]
    }}).is_valid(fresh)
    assert not Draft202012Validator({"properties": {
        "schema_version": historical["properties"]["schema_version"],
        "authorized_actions": historical["properties"]["authorized_actions"]
    }}).is_valid(fresh)


def test_actual_committed_legacy_envelope_historical_readback_only():
    import yaml
    from jsonschema import Draft202012Validator
    old_schema = json.loads((ROOT / "schemas/historical/g2-execution-envelope-v1.0.schema.json").read_text())
    old_path = ROOT / ".gwc/tasks/SCRUM-668/g2/execution-envelope.yaml"
    persisted = yaml.safe_load(old_path.read_text())
    assert persisted["schema_version"] == "1.0"
    assert {"add_files", "stage_commit_push"} <= set(persisted["authorized_actions"])
    assert list(Draft202012Validator(old_schema).iter_errors(persisted)) == []
    assert list(Draft202012Validator(SCHEMA).iter_errors(persisted)) != []
    # Readback of legacy ACTIVE is not a new approval or an executable capability.
    assert persisted["activation_state"] == "ACTIVE"
