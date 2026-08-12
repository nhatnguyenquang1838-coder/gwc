from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "tools/node_architect/files_read_scope.py"
SCHEMA = ROOT / "schemas/bounded-read-scope.schema.json"
TASK = "SCRUM-303"
REPO = "nhatnguyenquang1838-coder/gwc"
BASE = "5" * 40
BRANCH = "auto/SCRUM-303-na81-20260810"


def load_module():
    spec = importlib.util.spec_from_file_location("files_read_scope", MODULE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FilesReadScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_module()
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        cls.validator = Draft202012Validator(schema)

    def payload(self):
        return {
            "task_id": TASK,
            "repository": REPO,
            "base_sha": BASE,
            "branch": BRANCH,
            "allowed_roots": ["core", "schemas", "tools", "tests"],
            "repository_paths": [
                "core/node-architect/node-catalog/intake_context/files-read-scope.node.json",
                "schemas/bounded-read-scope.schema.json",
                "tools/node_architect/files_read_scope.py",
                "tests/test_intake_context_files_read_scope.py",
            ],
            "read_requirements": [
                {
                    "requirement_id": "descriptor",
                    "candidates": ["core/node-architect/node-catalog/intake_context/files-read-scope.node.json"],
                    "reason": "Bind the canonical node descriptor.",
                },
                {
                    "requirement_id": "evaluator",
                    "candidates": ["tools/node_architect/files_read_scope.py"],
                    "reason": "Inspect the executable evaluator.",
                },
            ],
            "excluded_paths": [
                {"path": "tests", "reason": "Tests are not required by this analysis slice.", "match": "prefix"}
            ],
            "source_bindings": [
                {"source_type": "repository", "ref": "pre-prod", "revision": BASE, "status": "VERIFIED"},
                {"source_type": "ua", "ref": "SCRUM-303", "revision": "ua-v1", "status": "VERIFIED"},
            ],
            "repository_snapshot": {"base_sha": BASE, "tree_digest": "sha256:" + "1" * 64},
            "ua_snapshot": {"base_sha": BASE, "digest": "sha256:" + "2" * 64},
            "observed_at": "2026-08-10T03:30:00Z",
        }

    def render(self, **changes):
        payload = copy.deepcopy(self.payload())
        payload.update(changes)
        return self.mod.render_files_read_scope(payload)

    def assert_schema(self, artifact):
        errors = list(self.validator.iter_errors(artifact))
        self.assertEqual([], [error.message for error in errors])

    def test_minimum_verified_scope_is_ready_and_schema_valid(self):
        artifact = self.render()
        self.assertEqual("READY", artifact["outcome"])
        self.assertEqual(
            [
                "core/node-architect/node-catalog/intake_context/files-read-scope.node.json",
                "tools/node_architect/files_read_scope.py",
            ],
            artifact["files_read"],
        )
        self.assertEqual("ACCEPTED", artifact["reason_code"])
        self.assert_schema(artifact)

    def test_explicit_exclusion_is_recorded_with_reason(self):
        payload = self.payload()
        payload["read_requirements"].append({
            "requirement_id": "optional-test",
            "candidates": ["tests/test_intake_context_files_read_scope.py", "schemas/bounded-read-scope.schema.json"],
            "reason": "One verified contract source is enough.",
        })
        artifact = self.mod.render_files_read_scope(payload)
        self.assertEqual("READY", artifact["outcome"])
        self.assertIn("tests/test_intake_context_files_read_scope.py", artifact["files_exclude"])
        self.assertEqual("Tests are not required by this analysis slice.", artifact["exclusion_reasons"]["tests/test_intake_context_files_read_scope.py"])
        self.assert_schema(artifact)

    def test_outside_allowed_root_fails_closed_without_broadening(self):
        payload = self.payload()
        payload["read_requirements"][0]["candidates"] = [".github/workflows/validate-instructions.yml"]
        artifact = self.mod.render_files_read_scope(payload)
        self.assertEqual(("BLOCKED", "SCOPE_DRIFT", "RECOMPUTE_READ_SCOPE"), (artifact["outcome"], artifact["reason_code"], artifact["next_route"]))
        self.assertEqual([], artifact["files_read"])
        self.assertIn(".github/workflows/validate-instructions.yml", artifact["files_exclude"])
        self.assertEqual("Outside verified allowed roots.", artifact["exclusion_reasons"][".github/workflows/validate-instructions.yml"])
        self.assert_schema(artifact)

    def test_ambiguous_candidates_fail_closed(self):
        payload = self.payload()
        payload["read_requirements"][1]["candidates"] = [
            "tools/node_architect/files_read_scope.py",
            "schemas/bounded-read-scope.schema.json",
        ]
        artifact = self.mod.render_files_read_scope(payload)
        self.assertEqual(("BLOCKED", "MALFORMED_INPUT", "CLARIFY_READ_SCOPE"), (artifact["outcome"], artifact["reason_code"], artifact["next_route"]))
        self.assert_schema(artifact)

    def test_missing_required_path_fails_closed(self):
        payload = self.payload()
        payload["read_requirements"][1]["candidates"] = ["tools/node_architect/missing.py"]
        artifact = self.mod.render_files_read_scope(payload)
        self.assertEqual(("BLOCKED", "MISSING_EVIDENCE", "REPOSITORY_EVIDENCE_MISSING"), (artifact["outcome"], artifact["reason_code"], artifact["failure_classification"]))
        self.assertIn("tools/node_architect/missing.py", artifact["files_missing"])
        self.assert_schema(artifact)

    def test_repository_or_ua_drift_invalidates_scope(self):
        artifact = self.render(repository_snapshot={"base_sha": "6" * 40, "tree_digest": "sha256:" + "1" * 64})
        self.assertEqual(("BLOCKED", "SCOPE_DRIFT", "RECOMPUTE_READ_SCOPE"), (artifact["outcome"], artifact["reason_code"], artifact["next_route"]))
        self.assert_schema(artifact)

    def test_stale_source_binding_invalidates_scope(self):
        payload = self.payload()
        payload["source_bindings"][0]["status"] = "STALE"
        artifact = self.mod.render_files_read_scope(payload)
        self.assertEqual(("BLOCKED", "SCOPE_DRIFT"), (artifact["outcome"], artifact["reason_code"]))
        self.assert_schema(artifact)

    def test_malformed_source_bindings_block_with_schema_valid_artifact(self):
        artifact = self.render(source_bindings=[])
        self.assertEqual(("BLOCKED", "MALFORMED_INPUT", "RECOMPUTE_READ_SCOPE"), (artifact["outcome"], artifact["reason_code"], artifact["next_route"]))
        self.assertEqual([], artifact["source_bindings"])
        self.assert_schema(artifact)

    def test_scope_hash_is_deterministic_across_order_and_observation_time(self):
        first = self.render()
        payload = self.payload()
        payload["read_requirements"].reverse()
        payload["repository_paths"].reverse()
        payload["source_bindings"].reverse()
        payload["observed_at"] = "2099-01-01T00:00:00Z"
        second = self.mod.render_files_read_scope(payload)
        self.assertEqual(first["scope_hash"], second["scope_hash"])

    def test_prior_scope_from_another_base_is_stale(self):
        artifact = self.render(prior_scope={"base_sha": "7" * 40, "scope_hash": "sha256:" + "3" * 64})
        self.assertEqual(("BLOCKED", "SCOPE_DRIFT"), (artifact["outcome"], artifact["reason_code"]))
        self.assert_schema(artifact)

    def test_same_base_source_revision_drift_invalidates_prior_scope(self):
        first = self.render()
        payload = self.payload()
        payload["prior_scope"] = {"base_sha": BASE, "scope_hash": first["scope_hash"]}
        payload["source_bindings"][1]["revision"] = "ua-v2"
        payload["ua_snapshot"]["digest"] = "sha256:" + "9" * 64
        artifact = self.mod.render_files_read_scope(payload)
        self.assertEqual(("BLOCKED", "SCOPE_DRIFT", "RECOMPUTE_READ_SCOPE"), (artifact["outcome"], artifact["reason_code"], artifact["next_route"]))
        self.assert_schema(artifact)

    def test_all_candidates_excluded_is_scope_drift_not_missing_evidence(self):
        payload = self.payload()
        payload["read_requirements"] = [{
            "requirement_id": "test-only",
            "candidates": ["tests/test_intake_context_files_read_scope.py"],
            "reason": "Test-only path is intentionally excluded.",
        }]
        artifact = self.mod.render_files_read_scope(payload)
        self.assertEqual(("BLOCKED", "SCOPE_DRIFT"), (artifact["outcome"], artifact["reason_code"]))
        self.assertEqual([], artifact["files_missing"])
        self.assertIn("tests/test_intake_context_files_read_scope.py", artifact["files_exclude"])
        self.assert_schema(artifact)

    def test_no_authority_is_ever_granted(self):
        artifact = self.render()
        self.assertTrue(artifact["read_only_projection"])
        self.assertFalse(any(value for key, value in artifact.items() if key.endswith("authority_granted")))

    def test_legacy_payload_remains_compatible(self):
        artifact = self.mod.render_files_read_scope({
            "task_id": TASK,
            "repository": REPO,
            "base_sha": BASE,
            "branch": BRANCH,
            "governance_reads": ["AGENTS.md", "core/Coding_Project_Governance_v1.0.md", "AGENTS.md"],
            "task_reads": ["projects/gwc/project-profile.yaml"],
        })
        self.assertEqual("READY", artifact["outcome"])
        self.assertEqual(
            ["AGENTS.md", "core/Coding_Project_Governance_v1.0.md", "projects/gwc/project-profile.yaml"],
            artifact["files_read"],
        )
        self.assert_schema(artifact)

    def test_legacy_unsafe_path_still_raises(self):
        with self.assertRaises(ValueError):
            self.mod.render_files_read_scope({
                "task_id": TASK,
                "repository": REPO,
                "base_sha": BASE,
                "branch": BRANCH,
                "files_read": ["../escape.md"],
            })


if __name__ == "__main__":
    unittest.main()
