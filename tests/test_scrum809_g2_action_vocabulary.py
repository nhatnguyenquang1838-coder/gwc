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
