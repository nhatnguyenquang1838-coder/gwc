from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "validate_g5_recovery_authority.py"
SCHEMA = ROOT / "schemas" / "g5-recovery-authority.schema.json"
TEMPLATE = ROOT / "templates" / "gates" / "g5-recovery-authority.template.json"
WORKFLOW = ROOT / ".github" / "workflows" / "g4-g5-evidence.yml"

SPEC = importlib.util.spec_from_file_location("validate_g5_recovery_authority", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class G5RecoveryAuthorityTests(unittest.TestCase):
    def load(self) -> tuple[dict, dict]:
        return json.loads(TEMPLATE.read_text()), json.loads(SCHEMA.read_text())

    def test_template_passes(self) -> None:
        record, schema = self.load()
        issues = MODULE.validate_record(record, schema, now=datetime(2026, 8, 1, 13, 0, tzinfo=timezone.utc))
        self.assertEqual([], issues)

    def test_expired_recovery_fails(self) -> None:
        record, schema = self.load()
        issues = MODULE.validate_record(record, schema, now=datetime(2026, 8, 3, tzinfo=timezone.utc))
        self.assertTrue(any("expired" in issue for issue in issues))

    def test_wrong_sha_or_duplicate_run_fails(self) -> None:
        record, schema = self.load()
        record["required_workflows"][0]["head_sha"] = "c" * 40
        record["required_workflows"][1]["run_id"] = record["required_workflows"][0]["run_id"]
        issues = MODULE.validate_record(record, schema, now=datetime(2026, 8, 1, 13, 0, tzinfo=timezone.utc))
        self.assertTrue(any("head_sha" in issue for issue in issues))
        self.assertTrue(any("distinct" in issue for issue in issues))

    def test_manual_action_and_recursive_pr_fail_schema(self) -> None:
        record, schema = self.load()
        record["manual_action_authorized"] = True
        record["no_recursive_evidence_pr"] = False
        issues = MODULE.validate_record(record, schema, now=datetime(2026, 8, 1, 13, 0, tzinfo=timezone.utc))
        self.assertTrue(any("manual_action_authorized" in issue for issue in issues))
        self.assertTrue(any("no_recursive_evidence_pr" in issue for issue in issues))

    def test_workflow_binds_exact_recovery_and_idempotency(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        for marker in (
            "APPROVE G5 RECOVERY",
            "bootstrap_manual_authority",
            "getWorkflowRun",
            "mergeCommit.commit?.message",
            "source_digest",
            "gwc:g5-recovery-authority",
            "conflicting trusted G5 recovery receipt",
            "duplicate",
            "materialize_g5_recovery_evidence",
        ):
            self.assertIn(marker, text)
        self.assertNotIn("git push", text)
        self.assertNotIn("create_pull_request", text)


if __name__ == "__main__":
    unittest.main()
