from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


class DwcConnectorCapabilityContractTests(unittest.TestCase):
    def test_human_approved_merge_is_declared_and_not_hard_excluded(self):
        capabilities = yaml.safe_load((ROOT / "agents/dwc/capabilities.yaml").read_text(encoding="utf-8"))

        bounded = capabilities["capabilities"]["bounded_write_on_guarded_branch"]
        self.assertTrue(bounded["merge_human_approved_pull_request"])

        hard_exclusions = set(capabilities["hard_exclusions"])
        self.assertNotIn("merge", hard_exclusions)
        self.assertIn("merge_without_exact_g4_human_approval", hard_exclusions)

    def test_ready_for_review_capability_is_g3_metadata_only(self):
        capabilities = yaml.safe_load((ROOT / "agents/dwc/capabilities.yaml").read_text(encoding="utf-8"))

        bounded = capabilities["capabilities"]["bounded_write_on_guarded_branch"]
        ready = bounded["mark_pr_ready_for_review"]

        self.assertEqual(ready["tool"], "github_mark_pr_ready_for_review")
        self.assertFalse(ready["approval"]["required"])
        self.assertIn("expected_head_sha == current_head_sha", ready["guard"])
        self.assertIn("g3_delivery_record == PASS", ready["guard"])
        self.assertIn("no_merge_permission", ready["guard"])
        self.assertIn("Does not grant G4 merge authority.", ready["notes"])

    def test_ready_for_review_action_can_be_scoped_in_approval_envelope(self):
        schema = (ROOT / "schemas/approval-envelope.schema.json").read_text(encoding="utf-8")

        self.assertIn('"mark_pr_ready_for_review"', schema)
        self.assertIn('"merge_approved_pr"', schema)

    def test_runtime_instruction_requires_github_merge_pr_tool_or_manual_blocker(self):
        instructions = (ROOT / "agents/dwc/agent-instructions.md").read_text(encoding="utf-8")

        self.assertIn("github_merge_pr", instructions)
        self.assertIn("exact G4 approval command", instructions)
        self.assertIn("approved PR head SHA", instructions)
        self.assertIn("manual-merge blocker", instructions)

    def test_runtime_instruction_defines_ready_for_review_tool_contract(self):
        instructions = (ROOT / "agents/dwc/agent-instructions.md").read_text(encoding="utf-8")

        self.assertIn("github_mark_pr_ready_for_review", instructions)
        self.assertIn("expected_head_sha", instructions)
        self.assertIn("required CI is `success`", instructions)
        self.assertIn("G3 delivery record are non-stale", instructions)
        self.assertIn("ready-for-review blocker", instructions)
        self.assertIn("This action grants no merge permission", instructions)


if __name__ == "__main__":
    unittest.main()
