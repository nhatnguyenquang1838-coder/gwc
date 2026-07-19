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

    def test_runtime_instruction_requires_github_merge_pr_tool_or_manual_blocker(self):
        instructions = (ROOT / "agents/dwc/agent-instructions.md").read_text(encoding="utf-8")

        self.assertIn("github_merge_pr", instructions)
        self.assertIn("exact G4 approval command", instructions)
        self.assertIn("approved PR head SHA", instructions)
        self.assertIn("manual-merge blocker", instructions)


if __name__ == "__main__":
    unittest.main()
