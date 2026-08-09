#!/usr/bin/env python3
"""Focused + neighbor regression tests for intake_context.repo-identity-check (SCRUM-300)."""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas/repo-identity.schema.json"
EVAL = ROOT / "tools/node_architect/repo_identity_check.py"

VERIFIED = {
    "owner": "nhatnguyenquang1838-coder",
    "name": "gwc",
    "default_branch": "main",
    "protected_branch": "pre-prod",
    "execution_mode": "PREPROD_AUTONOMOUS",
}


def _load_module():
    spec = importlib.util.spec_from_file_location("repo_identity_check", EVAL)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _load_schema():
    import jsonschema
    from jsonschema import Draft202012Validator
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema


M = _load_module()
SCHEMA_OBJ = _load_schema()
from jsonschema import Draft202012Validator
VALIDATOR = Draft202012Validator(SCHEMA_OBJ)

TASK = "SCRUM-300"
REPO = "nhatnguyenquang1838-coder/gwc"
BASE = "79c3091c0f16c9f8e3e6b6d9f0a1b2c3d4e5f607"  # pre-prod base sha bound for this task


def _assert_valid(self, art):
    errors = sorted(VALIDATOR.iter_errors(art), key=lambda e: list(e.path))
    self.assertEqual([], [f"{'/'.join(map(str,e.path))}: {e.message}" for e in errors],
                     msg=json.dumps(art, indent=2))
    for f in M.AUTH_FIELDS:
        self.assertFalse(art[f], f"{f} must be false")
    self.assertTrue(art["read_only_projection"])
    # decision_digest must be a valid sha256 and stable for same input
    self.assertTrue(art["decision_digest"].startswith("sha256:"))


class RepoIdentityCheckTests(unittest.TestCase):
    def test_accepted_well_formed_identity(self):
        art = M.render_repo_identity_check(
            task_id=TASK, repository=REPO, base_sha=BASE,
            observed_identity=dict(VERIFIED),
            verified_source=dict(VERIFIED),
            observed_at="2026-08-09T18:40:00+07:00",
        )
        self.assertEqual("ACCEPTED", art["outcome"])
        self.assertTrue(art["identity_match"])
        self.assertIn("ACCEPTED", art["reason_codes"])
        _assert_valid(self, art)

    def test_repo_mismatch_blocks(self):
        observed = dict(VERIFIED, owner="someone-else", name="other-repo")
        art = M.render_repo_identity_check(
            task_id=TASK, repository=REPO, base_sha=BASE,
            observed_identity=observed, verified_source=dict(VERIFIED),
        )
        self.assertEqual("BLOCKED", art["outcome"])
        self.assertIn("REPO_MISMATCH", art["reason_codes"])
        self.assertFalse(art["identity_match"])
        _assert_valid(self, art)

    def test_default_branch_mismatch_blocks(self):
        observed = dict(VERIFIED, default_branch="release")
        art = M.render_repo_identity_check(
            task_id=TASK, repository=REPO, base_sha=BASE,
            observed_identity=observed, verified_source=dict(VERIFIED),
        )
        self.assertEqual("BLOCKED", art["outcome"])
        self.assertIn("DEFAULT_BRANCH_MISMATCH", art["reason_codes"])
        _assert_valid(self, art)

    def test_protected_branch_mismatch_blocks(self):
        observed = dict(VERIFIED, protected_branch="main")
        art = M.render_repo_identity_check(
            task_id=TASK, repository=REPO, base_sha=BASE,
            observed_identity=observed, verified_source=dict(VERIFIED),
        )
        self.assertEqual("BLOCKED", art["outcome"])
        self.assertIn("PROTECTED_BRANCH_MISMATCH", art["reason_codes"])
        _assert_valid(self, art)

    def test_execution_mode_mismatch_blocks(self):
        observed = dict(VERIFIED, execution_mode="MAIN_GOVERNANCE")
        art = M.render_repo_identity_check(
            task_id=TASK, repository=REPO, base_sha=BASE,
            observed_identity=observed, verified_source=dict(VERIFIED),
        )
        self.assertEqual("BLOCKED", art["outcome"])
        self.assertIn("EXECUTION_MODE_MISMATCH", art["reason_codes"])
        _assert_valid(self, art)

    def test_evidence_gap_when_observed_missing(self):
        art = M.render_repo_identity_check(
            task_id=TASK, repository=REPO, base_sha=BASE,
            observed_identity={"owner": "x"},  # missing required keys
            verified_source=dict(VERIFIED),
        )
        self.assertIn("EVIDENCE_GAP", art["reason_codes"])
        self.assertNotEqual("ACCEPTED", art["outcome"])
        self.assertFalse(art["identity_match"])

    def test_evidence_gap_when_verified_missing(self):
        art = M.render_repo_identity_check(
            task_id=TASK, repository=REPO, base_sha=BASE,
            observed_identity=dict(VERIFIED),
            verified_source={"owner": "x"},
        )
        self.assertIn("EVIDENCE_GAP", art["reason_codes"])
        self.assertNotEqual("ACCEPTED", art["outcome"])
        self.assertFalse(art["identity_match"])

    def test_malformed_repository(self):
        art = M.render_repo_identity_check(
            task_id=TASK, repository="not-a-repo", base_sha=BASE,
            observed_identity=dict(VERIFIED), verified_source=dict(VERIFIED),
        )
        self.assertIn("MALFORMED_INPUT", art["reason_codes"])
        # schema must reject the malformed repository string
        schema_errors = list(VALIDATOR.iter_errors(art))
        self.assertTrue(schema_errors, "schema should reject malformed repository")
        self.assertTrue(any("repository" in "/".join(map(str, e.path)) for e in schema_errors))

    def test_malformed_base_sha(self):
        art = M.render_repo_identity_check(
            task_id=TASK, repository=REPO, base_sha="xyz",  # not 40 hex
            observed_identity=dict(VERIFIED), verified_source=dict(VERIFIED),
        )
        self.assertIn("MALFORMED_INPUT", art["reason_codes"])
        schema_errors = list(VALIDATOR.iter_errors(art))
        self.assertTrue(schema_errors, "schema should reject malformed base_sha")
        self.assertTrue(any("base_sha" in "/".join(map(str, e.path)) for e in schema_errors))

    def test_idempotent_digest(self):
        a = M.render_repo_identity_check(
            task_id=TASK, repository=REPO, base_sha=BASE,
            observed_identity=dict(VERIFIED), verified_source=dict(VERIFIED),
        )
        b = M.render_repo_identity_check(
            task_id=TASK, repository=REPO, base_sha=BASE,
            observed_identity=dict(VERIFIED), verified_source=dict(VERIFIED),
        )
        self.assertEqual(a["decision_digest"], b["decision_digest"])

    def test_no_authority_granted_ever(self):
        art = M.render_repo_identity_check(
            task_id=TASK, repository=REPO, base_sha=BASE,
            observed_identity=dict(VERIFIED), verified_source=dict(VERIFIED),
        )
        for f in M.AUTH_FIELDS:
            self.assertFalse(art[f])


if __name__ == "__main__":
    unittest.main(verbosity=2)
