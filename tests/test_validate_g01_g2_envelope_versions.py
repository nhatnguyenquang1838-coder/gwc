"""Regression tests for explicit G2 envelope versions and validator compatibility."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile

from jsonschema import Draft202012Validator, FormatChecker
import yaml

import tools.validate_g01 as validate_g01_module
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


def test_validate_gate_artifact_supports_current_and_legacy_keyword_call_forms() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    current = validate_gate_artifact(repo_root, repo_root, "G2_EXECUTION", {})
    legacy = validate_gate_artifact(repo_root, "G2_EXECUTION", {})
    keyword = validate_gate_artifact(
        workspace=repo_root,
        gate="G2_EXECUTION",
        artifacts={},
    )

    assert [issue.code for issue in legacy] == [issue.code for issue in current]
    assert [issue.code for issue in keyword] == [issue.code for issue in current]
    assert keyword[0].code == "GATE_ARTIFACT_MISSING"


def test_historical_unversioned_scrum188_envelope_uses_explicit_compatibility() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    source = repo_root / ".gwc" / "tasks" / "SCRUM-188" / "g2" / "execution-envelope.yaml"
    with tempfile.TemporaryDirectory(prefix="hermes-verify-") as directory:
        workspace = Path(directory)
        target = workspace / "g2" / "execution-envelope.yaml"
        target.parent.mkdir(parents=True)
        shutil.copyfile(source, target)

        issues = validate_gate_artifact(repo_root, workspace, "G2_EXECUTION", {})

    assert issues == []


def test_unversioned_modern_envelope_does_not_bypass_strict_validation() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    envelope = _envelope("1.1", CANONICAL_ACTIONS)
    envelope.pop("schema_version")
    with tempfile.TemporaryDirectory(prefix="hermes-verify-") as directory:
        workspace = Path(directory)
        target = workspace / "g2" / "execution-envelope.yaml"
        target.parent.mkdir(parents=True)
        target.write_text(yaml.safe_dump(envelope), encoding="utf-8")

        issues = validate_gate_artifact(repo_root, workspace, "G2_EXECUTION", {})

    assert any(issue.code == "G2_LEGACY_UNVERSIONED_SIGNATURE_INVALID" for issue in issues)


OBSERVED_LEGACY_PROFILE_PATHS = [
    ".gwc/tasks/GWC-P1-FOLLOWUP-GRAPH-REVISION/g2/execution-envelope.yaml",
    ".gwc/tasks/SCRUM-104/g2/execution-envelope.yaml",
    ".gwc/tasks/SCRUM-108/g2/execution-envelope.yaml",
    ".gwc/tasks/SCRUM-109/g2/execution-envelope.yaml",
    ".gwc/tasks/SCRUM-115/g2/execution-envelope.yaml",
    ".gwc/tasks/SCRUM-116/g2/execution-envelope.yaml",
    ".gwc/tasks/SCRUM-117/g2/execution-envelope.yaml",
    ".gwc/tasks/SCRUM-118/g2/execution-envelope.yaml",
    ".gwc/tasks/SCRUM-138/g2/execution-envelope.yaml",
    ".gwc/tasks/SCRUM-139/g2/execution-envelope.yaml",
    ".gwc/tasks/SCRUM-140/g2/execution-envelope.yaml",
    ".gwc/tasks/SCRUM-143/g2/execution-envelope.yaml",
    ".gwc/tasks/SCRUM-185/g2/execution-envelope.yaml",
    ".gwc/tasks/SCRUM-186/g2/execution-envelope.yaml",
    ".gwc/tasks/SCRUM-188/g2/execution-envelope.yaml",
    ".gwc/tasks/SCRUM-190/g2/execution-envelope.yaml",
    ".gwc/tasks/SCRUM-191/g2/execution-envelope.yaml",
    ".gwc/tasks/SCRUM-192/g2/execution-envelope.yaml",
    ".gwc/tasks/SCRUM-208/g2/execution-envelope.yaml",
    ".gwc/tasks/SCRUM-230/g2/execution-envelope.yaml",
    ".gwc/tasks/SCRUM-232/g2/execution-envelope.yaml",
]


def _legacy_issues(repo_root: Path, document: object) -> list[object]:
    with tempfile.TemporaryDirectory(prefix="hermes-verify-") as directory:
        workspace = Path(directory)
        target = workspace / "g2" / "execution-envelope.yaml"
        target.parent.mkdir(parents=True)
        target.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
        return validate_gate_artifact(repo_root, workspace, "G2_EXECUTION", {})


def test_legacy_registry_is_built_from_fourteen_observed_profiles() -> None:
    registry = getattr(validate_g01_module, "LEGACY_UNVERSIONED_PROFILE_REGISTRY", ())
    assert len(registry) == 14


def test_all_observed_legacy_mapping_artifacts_validate() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    for relative_path in OBSERVED_LEGACY_PROFILE_PATHS:
        source = repo_root / relative_path
        document = yaml.safe_load(source.read_text(encoding="utf-8"))
        assert _legacy_issues(repo_root, document) == [], relative_path


def test_legacy_signature_rejects_foreign_or_malformed_identity() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    source = repo_root / ".gwc" / "tasks" / "SCRUM-188" / "g2" / "execution-envelope.yaml"
    baseline = yaml.safe_load(source.read_text(encoding="utf-8"))
    mutations = {
        "task_id": "SCRUM-999",
        "repository": "foreign/repository",
        "base_sha": "not-a-sha",
        "working_branch": "foreign/branch",
        "scope_hash": "not-a-scope-hash",
        "approval_id": "FOREIGN-APPROVAL",
        "risk_class": "R9",
        "scope_version": -1,
        "scope_version_bool": True,
        "missing_risk": None,
        "extra_field": "unexpected",
    }

    for field, value in mutations.items():
        document = dict(baseline)
        if field == "scope_version_bool":
            document["scope_version"] = value
        elif field == "missing_risk":
            document.pop("risk_class")
        elif field == "extra_field":
            document[field] = value
        else:
            document[field] = value
        issues = _legacy_issues(repo_root, document)
        assert [issue.code for issue in issues] == [
            "G2_LEGACY_UNVERSIONED_SIGNATURE_INVALID"
        ], field


def test_legacy_signature_rejects_unknown_mixed_and_duplicate_actions() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    source = repo_root / ".gwc" / "tasks" / "SCRUM-188" / "g2" / "execution-envelope.yaml"
    baseline = yaml.safe_load(source.read_text(encoding="utf-8"))
    actions = list(baseline["authorized_actions"])
    invalid_action_lists = [
        actions[:-1] + ["invented_action"],
        [actions[0], "create_working_branch"],
        actions + [actions[-1]],
    ]

    for invalid_actions in invalid_action_lists:
        document = dict(baseline)
        document["authorized_actions"] = invalid_actions
        issues = _legacy_issues(repo_root, document)
        assert [issue.code for issue in issues] == [
            "G2_LEGACY_UNVERSIONED_SIGNATURE_INVALID"
        ]
