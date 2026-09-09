import json
from pathlib import Path

from jsonschema import Draft202012Validator

from tools.node_architect.g4_subject_container import validate_g4_subject_container
from tools.node_architect.scope_hash_calculation import calculate_gate_scope_identity

ROOT = Path(__file__).resolve().parents[1]
SUBJECT = "24c1426d634f7660879b10e340c0680c38b46efe"
CURRENT = "b63167bd8bb8a683e7336facd9b3183e3ff01f09"
SCOPE = "sha256:e34c9fbae88645b1ddb9265a9700fee3d2562a522d4b2916f390bcbe14568666"
G4_PATH = ".gwc/tasks/SCRUM-669/g4/merge-approval.yaml"

SCOPE_BASE = dict(
    task_id="SCRUM-669",
    repository="nhatnguyenquang1838-coder/gwc",
    base_ref="main",
    base_sha="0e752b04c9f40a04fe402a4f25fcb12c8b9b4d72",
    working_branch="impl/scrum-669-universal-run-e3-topology",
    head_sha=SUBJECT,
    risk_class="R2",
    authorized_paths=["tools/node_architect/universal_run_topology.py"],
    authorized_actions=["merge_approved_pr"],
    excluded_actions=["deploy_approved_release"],
    additional_bindings=[{"key": "pr_number", "value": "566"}],
)


def _subject_container(**overrides):
    data = dict(
        task_id="SCRUM-669",
        subject_head_sha=SUBJECT,
        current_head_sha=CURRENT,
        subject_scope_hash=SCOPE,
        subject_approved_paths=["tools/node_architect/universal_run_topology.py"],
        subject_to_current_delta_paths=[G4_PATH],
        subject_ancestor_verified=True,
        delta_complete_verified=True,
        receipt_approved_head_sha=CURRENT,
        receipt_scope_hash_prefix="e34c9fbae88645b1",
    )
    data.update(overrides)
    return validate_g4_subject_container(**data)


def test_scrum669_subject_scope_remains_valid():
    assert calculate_gate_scope_identity(**SCOPE_BASE)["outcome"] == "READY"


def test_g4_evidence_container_cannot_be_hashed_back_into_subject():
    out = calculate_gate_scope_identity(**{
        **SCOPE_BASE,
        "head_sha": CURRENT,
        "authorized_paths": SCOPE_BASE["authorized_paths"] + [G4_PATH],
    })
    assert out["outcome"] == "BLOCKED"
    assert "SCOPE_SELF_REFERENCE" in out["reason_codes"]
    assert out["scope_hash"] is None


def test_self_reference_blocked_result_is_schema_valid():
    schema = json.loads((ROOT / "schemas/node-architect/gate-authority/scope-hash-calculation.schema.json").read_text())
    out = calculate_gate_scope_identity(**{
        **SCOPE_BASE,
        "head_sha": CURRENT,
        "authorized_paths": [G4_PATH],
    })
    Draft202012Validator(schema).validate(out)


def test_scrum669_evidence_only_container_is_valid():
    assert _subject_container()["outcome"] == "PASS"


def test_subject_must_not_include_its_g4_artifact():
    out = _subject_container(subject_approved_paths=["tools/a.py", G4_PATH])
    assert "G4_SUBJECT_SELF_REFERENCE" in out["reason_codes"]


def test_non_g4_delta_after_subject_invalidates_g4():
    out = _subject_container(subject_to_current_delta_paths=[G4_PATH, "tools/changed.py"])
    assert "G4_CONTAINER_DELTA_NOT_EVIDENCE_ONLY" in out["reason_codes"]


def test_ancestry_and_complete_delta_are_required():
    assert "G4_SUBJECT_ANCESTRY_UNVERIFIED" in _subject_container(subject_ancestor_verified=False)["reason_codes"]
    assert "G4_CONTAINER_DELTA_NOT_EVIDENCE_ONLY" in _subject_container(delta_complete_verified=False)["reason_codes"]


def test_receipt_binds_current_head_and_subject_scope():
    assert "G4_RECEIPT_HEAD_MISMATCH" in _subject_container(receipt_approved_head_sha=SUBJECT)["reason_codes"]
    assert "G4_RECEIPT_SCOPE_MISMATCH" in _subject_container(receipt_scope_hash_prefix="0" * 16)["reason_codes"]


def test_no_recursive_second_g4_commit_when_subject_equals_current():
    out = _subject_container(
        current_head_sha=SUBJECT,
        subject_to_current_delta_paths=[],
        receipt_approved_head_sha=SUBJECT,
    )
    assert out["outcome"] == "PASS"
