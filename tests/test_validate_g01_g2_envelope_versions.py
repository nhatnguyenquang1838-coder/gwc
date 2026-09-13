"""Regression tests for explicit G2 envelope versions and validator compatibility."""
from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from tools.validate_g01 import validate_gate_artifact


LEGACY_ACTIONS = [
    "create_working_branch",
    "add_files",
    "run_sandboxed_validation",
    "stage_commit_push",
]
CANONICAL_ACTIONS = [
    "create_guarded_branch_or_worktree",
    "modify_approved_files",
    "run_sandboxed_validation",
    "stage",
    "create_commit",
    "push_working_branch",
]


def _envelope(version: str, actions: list[str]) -> dict[str, object]:
    return {
        "schema_version": version,
        "artifact_type": "g2-execution-envelope",
        "activation_state": "AWAITING_APPROVAL",
        "task_id": "SCRUM-781",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "base_ref": "fix/SCRUM-781-m1-runtime-contract-convergence",
        "base_sha": "5c4e4a53fe6ceaceac05f233409c3dd20f17f4f3",
        "working_branch": "fix/SCRUM-781-m2-r2-g2-schema-validator-repair",
        "risk_class": "R2",
        "risk_digest": "sha256:" + "b" * 64,
        "bounded_read_scope": [".gwc/tasks/SCRUM-781/**"],
        "bounded_write_scope": ["schemas/g2-execution-envelope.schema.json"],
        "authorized_actions": actions,
        "excluded_actions": ["g3_pr_promotion", "g4_merge", "g5_deploy", "g6_production"],
        "scope_hash": "sha256:" + "a" * 64,
        "f1_artifact_digests": {},
        "f2_digests": {},
        "approval_request_ref": None,
        "approval_validation_ref": None,
        "checkpoint_id": "cp-scrum781-versioned-test",
        "issued_at": "2026-09-13T16:00:00Z",
        "expires_at": "2026-09-13T19:00:00Z",
        "reason_code": "G2_ENVELOPE_AWAITING_APPROVAL",
        "envelope_digest": "sha256:" + "c" * 64,
        "exclusions": ["G3_PR", "G4_MERGE", "G5_DEPLOY", "G6_PRODUCTION"],
        "execution_started": False,
    }


def _errors(schema: dict[str, object], instance: dict[str, object]) -> list[str]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [error.message for error in validator.iter_errors(instance)]


def test_schema_version_dispatch_accepts_only_its_closed_vocabulary() -> None:
    schema_path = Path(__file__).resolve().parents[1] / "schemas" / "g2-execution-envelope.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    assert _errors(schema, _envelope("1.0", LEGACY_ACTIONS)) == []
    assert _errors(schema, _envelope("1.1", CANONICAL_ACTIONS)) == []
    assert _errors(schema, _envelope("1.0", CANONICAL_ACTIONS))
    assert _errors(schema, _envelope("1.1", LEGACY_ACTIONS))
    assert _errors(schema, _envelope("2.0", CANONICAL_ACTIONS))


def test_schema_rejects_mixed_and_unknown_action_vocabularies() -> None:
    schema_path = Path(__file__).resolve().parents[1] / "schemas" / "g2-execution-envelope.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    mixed = _envelope("1.1", [CANONICAL_ACTIONS[0], LEGACY_ACTIONS[1]])
    unknown = _envelope("1.1", CANONICAL_ACTIONS[:-1] + ["invented_action"])
    assert _errors(schema, mixed)
    assert _errors(schema, unknown)


def test_validate_gate_artifact_supports_current_and_legacy_call_forms() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    current = validate_gate_artifact(repo_root, repo_root, "G2_EXECUTION", {})
    legacy = validate_gate_artifact(repo_root, "G2_EXECUTION", {})

    assert [issue.code for issue in legacy] == [issue.code for issue in current]
    assert legacy[0].code == "GATE_ARTIFACT_MISSING"
