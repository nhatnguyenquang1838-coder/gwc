"""Contract tests for the temporary FastLane Bootstrap workflow."""

from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FastLaneBootstrapWorkflowTests(unittest.TestCase):
    def test_workflow_declares_temporary_bootstrap_and_sunset(self) -> None:
        workflow = ROOT / "core/workflows/GWC_FASTLANE_BOOTSTRAP_WORKFLOW_v0.1.md"
        content = workflow.read_text(encoding="utf-8")

        self.assertIn("Lifecycle: `temporary`", content)
        self.assertIn("Sunset condition", content)
        self.assertIn("does not grant merge", content)
        self.assertIn("direct write to `main`", content)

    def test_fastlane_schema_preserves_hard_gate_boundaries(self) -> None:
        schema_path = ROOT / "schemas/fastlane/fastlane-envelope.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        self.assertEqual(schema["properties"]["workflow"]["const"], "GWC_FASTLANE_BOOTSTRAP")
        self.assertTrue(schema["properties"]["temporary"]["const"])

        excluded = set(
            schema["properties"]["scope"]["properties"]["excluded_actions"]["items"]["enum"]
        )
        self.assertTrue(
            {
                "direct_push_main",
                "merge",
                "auto_merge",
                "deploy",
                "release",
                "production_config",
                "credentials",
                "secrets",
                "migration",
                "production_data",
            }.issubset(excluded)
        )

    def test_runbook_requires_exact_approval_and_draft_pr_stop(self) -> None:
        runbook = ROOT / "docs/runbooks/GWC_FASTLANE_BOOTSTRAP_RUNBOOK.md"
        content = runbook.read_text(encoding="utf-8")

        self.assertIn("APPROVE G2", content)
        self.assertIn("Draft PR", content)
        self.assertIn("Merge requires separate G4 approval", content)
        self.assertIn("main` still matches the envelope base SHA", content)


if __name__ == "__main__":
    unittest.main()
