"""Regression tests for consolidated gate lifecycle process rules."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class GateLifecycleProcessContractTests(unittest.TestCase):
    def read_text(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_g5_is_status_check_when_cicd_handles_deployment(self) -> None:
        gate_contract = self.read_text("core/GATE_LIFECYCLE_CONTRACT_v1.0.md")
        agents = self.read_text("AGENTS.md")
        dwc = self.read_text("agents/dwc/agent-instructions.md")
        chatgpt = self.read_text("agents/chatgpt-agent/agent-instructions.md")
        e2e = self.read_text("core/E2E_DRAFT_PR_DELIVERY_RULE.md")

        self.assertIn("When deployment is already automated by CI/CD, G5 is status verification only.", gate_contract)
        self.assertIn("G5 is a status/deployment verification gate.", agents)
        self.assertIn("G5 is status/deployment verification.", dwc)
        self.assertIn("For G5, do not infer a manual deploy/reload from the gate name.", chatgpt)
        self.assertIn("G5 checks those workflow/deployment statuses", e2e)

    def test_g6_is_not_generated_without_production_operation_scope(self) -> None:
        gate_contract = self.read_text("core/GATE_LIFECYCLE_CONTRACT_v1.0.md")
        agents = self.read_text("AGENTS.md")
        dwc = self.read_text("agents/dwc/agent-instructions.md")
        chatgpt = self.read_text("agents/chatgpt-agent/agent-instructions.md")

        expected = "G6 is generated only when production data, production configuration, migration, credential, or secret operations are actually in scope."
        self.assertIn(expected, agents)
        self.assertIn("generate a G6 approval request only when", gate_contract)
        self.assertIn("production data, production configuration, migrations, credentials, or secrets", dwc)
        self.assertIn("record `not_applicable`", chatgpt)

    def test_ds_admin_sync_and_late_reconciliation_are_required(self) -> None:
        gate_contract = self.read_text("core/GATE_LIFECYCLE_CONTRACT_v1.0.md")
        agents = self.read_text("AGENTS.md")
        dwc = self.read_text("agents/dwc/agent-instructions.md")
        chatgpt = self.read_text("agents/chatgpt-agent/agent-instructions.md")

        self.assertIn("Update the DS Admin task state through the legal State Engine transition", gate_contract)
        self.assertIn("The agent must synchronize DS Admin state before continuing across gate", agents)
        self.assertIn("## DS Admin state synchronization", dwc)
        self.assertIn("late reconciliation must be disclosed as late", chatgpt)

    def test_g4_ready_for_review_precheck_blocks_draft_pr_merge(self) -> None:
        gate_contract = self.read_text("core/GATE_LIFECYCLE_CONTRACT_v1.0.md")
        agents = self.read_text("AGENTS.md")
        dwc = self.read_text("agents/dwc/agent-instructions.md")
        e2e = self.read_text("core/E2E_DRAFT_PR_DELIVERY_RULE.md")

        self.assertIn("Draft Pull Request is not eligible for G4 merge execution", gate_contract)
        self.assertIn("A Draft PR is a G4 blocker", agents)
        self.assertIn("If the PR is still Draft", dwc)
        self.assertIn("Draft PR state is a G4 blocker", e2e)

    def test_approval_evidence_is_sanitized(self) -> None:
        agents = self.read_text("AGENTS.md")
        dwc = self.read_text("agents/dwc/agent-instructions.md")
        chatgpt = self.read_text("agents/chatgpt-agent/agent-instructions.md")

        self.assertIn("Do not copy full approval commands into commit messages", agents)
        self.assertIn("## Sanitized evidence notes", dwc)
        self.assertIn("Do not copy full executable approval commands into connector payloads", chatgpt)


if __name__ == "__main__":
    unittest.main()
