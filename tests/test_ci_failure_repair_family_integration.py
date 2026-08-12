"""M5 family integration for ci-failure-repair (SCRUM-322)."""
from __future__ import annotations

import json
import unittest

from tools.node_architect.ci_failure_repair import classify_ci_failure


class TestCiFailureRepairFamily(unittest.TestCase):
    def test_repo_delivery_family_boundary(self):
        result = classify_ci_failure(
            task_id="SCRUM-322",
            repository="nhatnguyenquang1838-coder/gwc",
            pr_number=42,
            head_sha="a" * 40,
            run_id="run-1",
            workflow_name="validate",
            failure_text="ModuleNotFoundError: No module named xyz",
            approved_file_scope=["tools/node_architect/ci_failure_repair.py"],
            event_id_or_idempotency_key="fam-1",
        )
        self.assertEqual(result["decision"], "REPAIR_REPOSITORY")
        self.assertEqual(result["artifact_type"], "ci-failure-repair")

    def test_no_authority_expansion(self):
        result = classify_ci_failure(
            task_id="SCRUM-322",
            repository="nhatnguyenquang1838-coder/gwc",
            pr_number=1,
            head_sha="b" * 40,
            run_id="run-2",
            workflow_name="validate",
            failure_text="flake8 E999 syntax error",
            approved_file_scope=["tools/node_architect/ci_failure_repair.py"],
            event_id_or_idempotency_key="fam-2",
        )
        self.assertFalse(result["execution_performed"])
        self.assertIn("bounded-pr:", result["remediation_scope"])
        # Must not imply merge, deploy, or production authority.
        self.assertNotIn("merge", (result["remediation_scope"] or "").lower())
        self.assertNotIn("deploy", (result["remediation_scope"] or "").lower())

    def test_external_block_prevents_side_effects(self):
        result = classify_ci_failure(
            task_id="SCRUM-322",
            repository="nhatnguyenquang1838-coder/gwc",
            pr_number=1,
            head_sha="b" * 40,
            run_id="run-3",
            workflow_name="validate",
            failure_text="Connection timed out while reaching upstream",
            event_id_or_idempotency_key="fam-3",
        )
        self.assertEqual(result["decision"], "EXTERNAL_BLOCKED")
        self.assertIsNone(result["remediation_scope"])

    def test_artifact_serializes_to_json(self):
        result = classify_ci_failure(
            task_id="SCRUM-322",
            repository="nhatnguyenquang1838-coder/gwc",
            pr_number=1,
            head_sha="b" * 40,
            run_id="run-4",
            workflow_name="validate",
            failure_text="ModuleNotFoundError: x",
            approved_file_scope=["a.py"],
            event_id_or_idempotency_key="fam-4",
        )
        blob = json.dumps(result, sort_keys=True)
        parsed = json.loads(blob)
        self.assertEqual(parsed["artifact_type"], "ci-failure-repair")


if __name__ == "__main__":
    unittest.main()
