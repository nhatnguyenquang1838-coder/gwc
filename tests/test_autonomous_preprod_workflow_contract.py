from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from tools.node_architect.autonomous_preprod_runtime import (
    BASE_SHA_MISMATCH,
    MAIN_TARGET_FORBIDDEN,
    REPOSITORY_BINDING_MISMATCH,
    execute_fixture_run,
)
from tests.test_run_graph_builder import BASE_SHA, manifest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/autonomous-preprod-runtime.yml"
REPOSITORY = "nhatnguyenquang1838-coder/gwc"


class AutonomousPreprodWorkflowContractTests(unittest.TestCase):
    def test_workflow_is_additive_exact_sha_and_no_pull_request_target(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch", text)
        self.assertIn("expected_base_sha", text)
        self.assertIn("git rev-parse HEAD", text)
        self.assertIn('--expected-repository "${{ github.repository }}"', text)
        self.assertIn('--expected-base-sha "${{ inputs.expected_base_sha }}"', text)
        self.assertIn("AUTONOMOUS_MAIN_TARGET_FORBIDDEN", text)
        self.assertIn("AUTONOMOUS_PR_HEAD_DRIFT", text)
        self.assertIn("autonomous-g4-evidence-bound", text)
        self.assertIn("gwc:g4-pr-evidence-receipt", text)
        self.assertIn("legacy G4 authority remains handled by the existing workflow", text)
        self.assertIn("steps.evidence.outputs.eligible == 'true'", text)
        self.assertNotIn("pull_request_target", text)
        parsed = yaml.load(text, Loader=yaml.BaseLoader)
        self.assertIn("workflow_dispatch", parsed["on"])
        self.assertEqual("write", parsed["permissions"]["checks"])
        self.assertEqual("read", parsed["permissions"]["contents"])

    def test_pull_request_contract_canary_is_exact_head_and_side_effect_free(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        parsed = yaml.load(text, Loader=yaml.BaseLoader)
        self.assertIn("contract-canary", parsed["jobs"])
        self.assertIn("github.event.pull_request.head.sha", text)
        self.assertIn("Materialize deterministic canary manifest", text)
        self.assertIn("fixture-pr-body.md", text)
        self.assertIn("Verify main-target denial before artifacts", text)
        self.assertIn("autonomous-contract-canary-${{ github.event.pull_request.head.sha }}", text)
        self.assertNotIn("pulls.update", text[text.index("contract-canary:"):text.index("g4-pr-evidence-authority:")])

    def test_runtime_blocks_main_before_any_side_effect(self):
        value = manifest()
        value.update({"pr_base": "main", "gate_statuses": {}, "validation": {}, "g4_readiness": {}})
        result, graph, story, body, block = execute_fixture_run(
            value,
            expected_repository=REPOSITORY,
            expected_base_sha=BASE_SHA,
        )
        self.assertEqual("BLOCKED", result["status"])
        self.assertEqual(MAIN_TARGET_FORBIDDEN, result["terminal_code"])
        self.assertFalse(result["side_effects_performed"])
        self.assertIsNone(graph)
        self.assertIsNone(story)
        self.assertIsNone(body)
        self.assertIsNone(block)

    def test_runtime_rejects_repository_binding_mismatch(self):
        value = manifest()
        value["pr_base"] = "pre-prod"
        result, graph, story, body, block = execute_fixture_run(
            value,
            expected_repository="other/repository",
            expected_base_sha=BASE_SHA,
        )
        self.assertEqual(REPOSITORY_BINDING_MISMATCH, result["terminal_code"])
        self.assertFalse(result["side_effects_performed"])
        self.assertIsNone(graph)
        self.assertIsNone(story)
        self.assertIsNone(body)
        self.assertIsNone(block)

    def test_runtime_rejects_checked_out_base_mismatch(self):
        value = manifest()
        value["pr_base"] = "pre-prod"
        result, graph, story, body, block = execute_fixture_run(
            value,
            expected_repository=REPOSITORY,
            expected_base_sha="f" * 40,
        )
        self.assertEqual(BASE_SHA_MISMATCH, result["terminal_code"])
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
        result, graph, story, body, block = execute_fixture_run(
            value,
            existing_pr_body="# Human\n",
            expected_repository=REPOSITORY,
            expected_base_sha=BASE_SHA,
        )
        self.assertEqual("PASS", result["status"])
        self.assertFalse(result["merge_authority_granted"])
        self.assertEqual(graph["graph_digest"], result["graph_digest"])
        self.assertEqual(story["story_digest"], result["story_digest"])
        self.assertIn("# Human", body)
        self.assertIn("GWC Autonomous Run Evidence", block)


if __name__ == "__main__":
    unittest.main()
