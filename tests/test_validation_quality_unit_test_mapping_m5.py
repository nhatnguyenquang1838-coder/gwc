"""M5 tests for validation_quality.unit-test-mapping (SCRUM-336 / #271).

Mirrors tests/test_validation_quality_ci_evidence_capture_m5.py and
tests/test_validation_quality_g3_pass_decision_m5.py. Validates the closed
decision schema plus the SCRUM-336 semantics: mapped-behavior PASS,
unmapped-change BLOCKED, missing/deleted-test BLOCKED, docs-only explicit
handling, overlap/conflict, policy drift, replay determinism, and the
non-authoritative guarantee (merge_authority_granted is always False).
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from tools.node_architect.unit_test_mapping import (
    BLOCKED,
    NODE_ID,
    PASS,
    REASON_CODES,
    map_unit_tests,
)

REPO = "nhatnguyenquang1838-coder/gwc"
BASE = "1" * 40
HEAD = "2" * 40
SCOPE = "sha256:" + "3" * 64
POLICY = "sha256:" + "4" * 64
BRANCH = "codex/scrum-336-validation-quality-unit-test-mapping-r3-20260814"


def evidence(**overrides) -> dict:
    p = {
        "task_id": "SCRUM-336",
        "run_id": "run-336",
        "repository": REPO,
        "branch": BRANCH,
        "base_sha": BASE,
        "head_sha": HEAD,
        "scope_hash": SCOPE,
        "graph_revision": "scrum-336-route-v1",
        "policy_digest": POLICY,
        "idempotency_key": "scrum-336-utm-1",
        "changed_artifacts": [],
        "test_inventory": [],
    }
    p.update(overrides)
    return p


class UnitTestMappingM5Tests(unittest.TestCase):
    def validate_schema(self, result):
        schema = json.loads(Path("schemas/unit-test-mapping-decision.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(result)

    def test_mapped_behavior_is_pass(self):
        r = map_unit_tests(evidence(
            changed_artifacts=["tools/node_architect/foo.py"],
            test_inventory=["tests/test_node_architect_runtime_m5.py"],
        ))
        self.assertEqual((r["status"], r["reason_code"]), (PASS, "MAPPED_PASS"))
        self.assertIn("tests/test_node_architect_runtime_m5.py", r["mapped_test_ids"])
        self.validate_schema(r)

    def test_unmapped_change_is_blocked(self):
        r = map_unit_tests(evidence(
            changed_artifacts=["src/unknown_module.py"],
            test_inventory=["tests/test_anything.py"],
        ))
        self.assertEqual((r["status"], r["reason_code"]), (BLOCKED, "UNMAPPED_CHANGE"))
        self.validate_schema(r)

    def test_missing_or_deleted_required_test_is_blocked(self):
        # A mapped runtime artifact whose required test is absent (deleted/missing).
        r = map_unit_tests(evidence(
            changed_artifacts=["tools/node_architect/foo.py"],
            test_inventory=[],  # required test not present -> missing/deleted
        ))
        self.assertEqual((r["status"], r["reason_code"]), (BLOCKED, "MISSING_REQUIRED_TEST"))
        self.validate_schema(r)

    def test_docs_only_is_explicit_not_guessed(self):
        r = map_unit_tests(evidence(
            changed_artifacts=["docs/guide.md", "README.md"],
            test_inventory=[],
        ))
        self.assertEqual((r["status"], r["reason_code"]), (PASS, "DOCS_ONLY"))
        for entry in r["mapping"]:
            self.assertEqual(entry["status"], "DOCS_ONLY")
            self.assertTrue(entry["docs_only"])
        self.validate_schema(r)

    def test_overlap_conflict_is_blocked(self):
        r = map_unit_tests(evidence(
            changed_artifacts=["tools/shared/helper.py"],
            test_inventory=["tests/test_shared_module_a.py", "tests/test_shared_module_b.py"],
        ))
        self.assertEqual((r["status"], r["reason_code"]), (BLOCKED, "MAPPING_CONFLICT"))
        self.validate_schema(r)

    def test_policy_drift_is_blocked(self):
        r = map_unit_tests(evidence(
            changed_artifacts=["tools/node_architect/foo.py"],
            test_inventory=["tests/test_node_architect_runtime_m5.py"],
        ), expected_policy_digest="sha256:" + "f" * 64)
        self.assertEqual((r["status"], r["reason_code"]), (BLOCKED, "POLICY_DRIFT"))
        self.validate_schema(r)

    def test_invalid_input_fails_closed(self):
        bad = evidence()
        bad["base_sha"] = "zzz"  # malformed SHA -> fail closed
        r = map_unit_tests(bad)
        self.assertEqual((r["status"], r["reason_code"]), (BLOCKED, "INVALID_INPUT"))
        # A fail-closed guard result legitimately carries the malformed identity,
        # so it is not expected to satisfy the canonical decision schema.
        self.assertFalse(r["merge_authority_granted"])
        self.assertFalse(r["deployment_authority_granted"])
        self.assertFalse(r["production_authority_granted"])

    def test_replay_is_deterministic(self):
        cache: dict = {}
        first = map_unit_tests(evidence(
            changed_artifacts=["tools/node_architect/foo.py"],
            test_inventory=["tests/test_node_architect_runtime_m5.py"],
        ), replay_cache=cache)
        second = map_unit_tests(evidence(
            changed_artifacts=["tools/node_architect/foo.py"],
            test_inventory=["tests/test_node_architect_runtime_m5.py"],
        ), replay_cache=cache)
        self.assertEqual(first["evidence_digest"], second["evidence_digest"])
        self.assertTrue(second["replayed"])
        self.validate_schema(second)

    def test_conflicting_identity_under_same_key_fails_closed(self):
        cache: dict = {}
        first = map_unit_tests(evidence(
            changed_artifacts=["tools/node_architect/foo.py"],
            test_inventory=["tests/test_node_architect_runtime_m5.py"],
        ), replay_cache=cache)
        other = evidence(head_sha="9" * 40, changed_artifacts=["src/unknown_module.py"], test_inventory=[])
        second = map_unit_tests(other, replay_cache=cache)
        self.assertEqual(first["reason_code"], "MAPPED_PASS")
        self.assertEqual((second["status"], second["reason_code"]), (BLOCKED, "CONFLICTING_IDENTITY"))
        self.validate_schema(second)

    def test_merge_authority_granted_is_always_false(self):
        for changed, inventory, expect_status in [
            (["tools/node_architect/foo.py"], ["tests/test_node_architect_runtime_m5.py"], PASS),
            (["src/unknown_module.py"], ["tests/test_anything.py"], BLOCKED),
        ]:
            r = map_unit_tests(evidence(changed_artifacts=changed, test_inventory=inventory))
            self.assertEqual(r["status"], expect_status)
            self.assertFalse(r["merge_authority_granted"])
            self.assertFalse(r["deployment_authority_granted"])
            self.assertFalse(r["production_authority_granted"])
            self.validate_schema(r)

    def test_reason_codes_are_closed_set(self):
        for code in REASON_CODES:
            self.assertIn(code, {
                "MAPPED_PASS", "DOCS_ONLY", "UNMAPPED_CHANGE", "MISSING_REQUIRED_TEST",
                "MAPPING_CONFLICT", "POLICY_DRIFT", "INVALID_INPUT", "CONFLICTING_IDENTITY",
            })
        self.assertEqual(NODE_ID, "validation_quality.unit-test-mapping")


if __name__ == "__main__":
    unittest.main()
