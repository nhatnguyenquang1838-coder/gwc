"""Contract tests for REVAMP_UPGRADE_GWC foundation artifacts."""

from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RevampUpgradeGwcWorkflowTests(unittest.TestCase):
    def test_revamp_workflow_preserves_source_of_truth_split(self) -> None:
        workflow = ROOT / "core/workflows/REVAMP_UPGRADE_GWC_WORKFLOW_v0.1.md"
        content = workflow.read_text(encoding="utf-8")

        self.assertIn("Workflow ID: `REVAMP_UPGRADE_GWC`", content)
        self.assertIn("Canonical coding state = GWC/Kiro checkpoint + Git delivery evidence", content)
        self.assertIn("External systems = audit projection", content)
        self.assertIn("does not", content)
        self.assertIn("merge without G4", content)

    def test_external_audit_projection_is_non_blocking(self) -> None:
        rule = ROOT / "core/node-architect/EXTERNAL_AUDIT_PROJECTION_RULE_v0.1.md"
        content = rule.read_text(encoding="utf-8")

        self.assertIn("External audit projection is non-blocking", content)
        self.assertIn("AUDIT_PENDING", content)
        self.assertIn("AUDIT_FAILED", content)
        self.assertIn("G4 merge approval", content)

        schema = json.loads(
            (ROOT / "schemas/node-architect/external-audit-projection.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(schema["properties"]["blocking"]["const"])
        target_props = schema["$defs"]["target"]["properties"]
        self.assertFalse(target_props["blocking"]["const"])

    def test_kiro_strict_coding_state_preserves_scope_controls(self) -> None:
        rule = ROOT / "core/node-architect/KIRO_STRICT_CODING_STATE_RULE_v0.1.md"
        content = rule.read_text(encoding="utf-8")

        self.assertIn("Preparation may be lean. Coding must be strict.", content)
        self.assertIn("Files WRITE", content)
        self.assertIn("BLOCKED_SCOPE_DRIFT", content)
        self.assertIn("merge", content)

        schema = json.loads(
            (ROOT / "schemas/node-architect/kiro-coding-state.schema.json").read_text(
                encoding="utf-8"
            )
        )
        states = set(schema["properties"]["state"]["enum"])
        self.assertIn("CODING_READY", states)
        self.assertIn("BLOCKED_APPROVAL_EXPIRED", states)
        excluded = set(schema["properties"]["scope"]["properties"]["excluded_actions"]["items"]["enum"])
        self.assertTrue({"direct_push_main", "merge", "deploy", "production_data"}.issubset(excluded))

    def test_revamp_envelope_schema_requires_hard_boundaries(self) -> None:
        schema = json.loads(
            (ROOT / "schemas/node-architect/revamp-upgrade-gwc-envelope.schema.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(schema["properties"]["workflow"]["const"], "REVAMP_UPGRADE_GWC")
        self.assertTrue(schema["properties"]["authority"]["properties"]["g2_approval_required"]["const"])
        self.assertTrue(schema["properties"]["authority"]["properties"]["g4_merge_approval_required"]["const"])
        self.assertFalse(schema["properties"]["authority"]["properties"]["g6_production_approval_required"]["const"])

    def test_runbook_requires_exact_approval_and_stops_before_merge(self) -> None:
        runbook = ROOT / "docs/runbooks/REVAMP_UPGRADE_GWC_RUNBOOK.md"
        content = runbook.read_text(encoding="utf-8")

        self.assertIn("APPROVE G2", content)
        self.assertIn("Do not proceed on plain", content)
        self.assertIn("G4 merge requires separate exact human approval", content)
        self.assertIn("Jira, TC, DS MCP", content)


if __name__ == "__main__":
    unittest.main()
