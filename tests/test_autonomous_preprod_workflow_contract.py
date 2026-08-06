from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from tools.node_architect.autonomous_preprod_runtime import MAIN_TARGET_FORBIDDEN, execute_fixture_run
from tests.test_run_graph_builder import manifest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/autonomous-preprod-runtime.yml"


class AutonomousPreprodWorkflowContractTests(unittest.TestCase):
    def test_workflow_is_additive_exact_sha_and_no_pull_request_target(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch", text)
        self.assertIn("expected_base_sha", text)
        self.assertIn("git rev-parse HEAD", text)
        self.assertIn("AUTONOMOUS_MAIN_TARGET_FORBIDDEN", text)
        self.assertIn("autonomous-g4-evidence-bound", text)
        self.assertIn("gwc:g4-pr-evidence-receipt", text)
        self.assertNotIn("pull_request_target", text)
        parsed = yaml.load(text, Loader=yaml.BaseLoader)
        self.assertIn("workflow_dispatch", parsed["on"])
        self.assertEqual("write", parsed["permissions"]["checks"])
        self.assertEqual("read", parsed["permissions"]["contents"])

    def test_runtime_blocks_main_before_any_side_effect(self):
        value = manifest()
        value.update({"pr_base": "main", "gate_statuses": {}, "validation": {}, "g4_readiness": {}})
        result, graph, story, body, block = execute_fixture_run(value)
        self.assertEqual("BLOCKED", result["status"])
        self.assertEqual(MAIN_TARGET_FORBIDDEN, result["terminal_code"])
        self.assertFalse(result["side_effects_performed"])
        self.assertIsNone(graph)
        self.assertIsNone(story)
        self.assertIsNone(body)
        self.assertIsNone(block)

    def test_fixture_run_produces_all_evidence_artifacts(self):
        value = manifest()
        value.update(
            {
                "pr_base": "pre-prod",
                "gate_statuses": {"G4_MERGE": "not_executed", "G5_DEPLOY": "not_executed", "G6_PRODUCTION_DATA": "not_applicable"},
                "validation": {"focused_tests": "PASS"},
                "g4_readiness": {"state": "not_ready"},
            }
        )
        result, graph, story, body, block = execute_fixture_run(value, existing_pr_body="# Human\n")
        self.assertEqual("PASS", result["status"])
        self.assertFalse(result["merge_authority_granted"])
        self.assertEqual(graph["graph_digest"], result["graph_digest"])
        self.assertEqual(story["story_digest"], result["story_digest"])
        self.assertIn("# Human", body)
        self.assertIn("GWC Autonomous Run Evidence", block)


if __name__ == "__main__":
    unittest.main()
