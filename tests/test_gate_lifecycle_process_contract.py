"""Regression tests for consolidated gate lifecycle process rules."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class GateLifecycleProcessContractTests(unittest.TestCase):
    def read_text(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def normalized_text(self, relative_path: str) -> str:
        return " ".join(self.read_text(relative_path).split())

    def test_g5_is_status_check_when_cicd_handles_deployment(self) -> None:
        gate_contract = self.normalized_text("core/GATE_LIFECYCLE_CONTRACT_v1.0.md")
        agents = self.normalized_text("AGENTS.md")
        dwc = self.normalized_text("agents/dwc/agent-instructions.md")
        chatgpt = self.normalized_text("agents/chatgpt-agent/agent-instructions.md")
        e2e = self.normalized_text("core/E2E_DRAFT_PR_DELIVERY_RULE.md")

        self.assertIn("When deployment is already automated by CI/CD, G5 is status verification only.", gate_contract)
        self.assertIn("G5 is a status/deployment verification gate.", agents)
        self.assertIn("G5 is status/deployment verification.", dwc)
        self.assertIn("For G5, do not infer a manual deploy/reload from the gate name.", chatgpt)
        self.assertIn("G5 checks those workflow/deployment statuses", e2e)
        self.assertIn("Read-only `G5_STATUS_VERIFY` starts automatically", gate_contract)
        self.assertIn("Read-only `G5_STATUS_VERIFY` runs automatically after G4 merge", e2e)

    def test_ready_for_review_is_g3_metadata_completion(self) -> None:
        gate_contract = self.normalized_text("core/GATE_LIFECYCLE_CONTRACT_v1.0.md")
        agents = self.normalized_text("AGENTS.md")
        dwc = self.normalized_text("agents/dwc/agent-instructions.md")
        chatgpt = self.normalized_text("agents/chatgpt-agent/agent-instructions.md")
        e2e = self.normalized_text("core/E2E_DRAFT_PR_DELIVERY_RULE.md")

        self.assertIn("Mark Draft PR ready for review after G3 `PASS`", gate_contract)
        self.assertIn("github_mark_pr_ready_for_review", dwc)
        self.assertIn("This transition is not merge approval", chatgpt)
        self.assertIn("G3 review decision does not authorize merge", e2e)
        self.assertIn("This ready-for-review transition is G3 metadata completion", agents)

    def test_chatgpt_gwc_responses_are_vietnamese_first(self) -> None:
        agents = self.normalized_text("AGENTS.md")
        chatgpt = self.normalized_text("agents/chatgpt-agent/agent-instructions.md")

        self.assertIn("ChatGPT-style agents operating in GWC project chat must respond Vietnamese-first", agents)
        self.assertIn("Status reports, blockers, evidence summaries, recommendations, and next actions should be written primarily in Vietnamese", chatgpt)

    def test_g6_is_not_generated_without_production_operation_scope(self) -> None:
        gate_contract = self.normalized_text("core/GATE_LIFECYCLE_CONTRACT_v1.0.md")
        agents = self.normalized_text("AGENTS.md")
        dwc = self.normalized_text("agents/dwc/agent-instructions.md")
        chatgpt = self.normalized_text("agents/chatgpt-agent/agent-instructions.md")

        expected = "G6 is generated only when production data, production configuration, migration, credential, or secret operations are actually in scope."
        self.assertIn(expected, agents)
        self.assertIn("generate a G6 approval request only when", gate_contract)
        self.assertIn("production data, production configuration, migrations, credentials, or secrets", dwc)
        self.assertIn("record `not_applicable`", chatgpt)

    def test_ds_admin_sync_and_late_reconciliation_are_required(self) -> None:
        gate_contract = self.normalized_text("core/GATE_LIFECYCLE_CONTRACT_v1.0.md")
        agents = self.normalized_text("AGENTS.md")
        dwc = self.normalized_text("agents/dwc/agent-instructions.md")
        chatgpt = self.normalized_text("agents/chatgpt-agent/agent-instructions.md")

        self.assertIn("Update the DS Admin task state through the legal State Engine transition", gate_contract)
        self.assertIn("The agent must synchronize DS Admin state before continuing across gate", agents)
        self.assertIn("## DS Admin state synchronization", dwc)
        self.assertIn("late reconciliation must be disclosed as late", chatgpt)

    def test_g4_ready_for_review_precheck_blocks_draft_pr_merge(self) -> None:
        gate_contract = self.normalized_text("core/GATE_LIFECYCLE_CONTRACT_v1.0.md")
        agents = self.normalized_text("AGENTS.md")
        dwc = self.normalized_text("agents/dwc/agent-instructions.md")
        e2e = self.normalized_text("core/E2E_DRAFT_PR_DELIVERY_RULE.md")

        self.assertIn("Draft Pull Request is not eligible for G4 merge execution", gate_contract)
        self.assertIn("A Draft PR is a G4 blocker", agents)
        self.assertIn("If the PR is still Draft", dwc)
        self.assertIn("Draft PR state is a G4 blocker", e2e)

    def test_approval_evidence_is_sanitized(self) -> None:
        agents = self.normalized_text("AGENTS.md")
        dwc = self.normalized_text("agents/dwc/agent-instructions.md")
        chatgpt = self.normalized_text("agents/chatgpt-agent/agent-instructions.md")

        self.assertIn("Do not copy full approval commands into commit messages", agents)
        self.assertIn("## Sanitized evidence notes", dwc)
        self.assertIn("Do not copy full executable approval commands into connector payloads", chatgpt)

    def test_g3_async_ci_continuation_uses_environment_aware_mechanism(self) -> None:
        gate_contract = self.normalized_text("core/GATE_LIFECYCLE_CONTRACT_v1.0.md")
        agents = self.normalized_text("AGENTS.md")
        dwc = self.normalized_text("agents/dwc/agent-instructions.md")
        e2e = self.normalized_text("core/E2E_DRAFT_PR_DELIVERY_RULE.md")

        self.assertIn("G3 asynchronous CI continuation", gate_contract)
        self.assertIn("webhook or CI event callback", gate_contract)
        self.assertIn("local sleep or poll loop", agents)
        self.assertIn("The default next-check interval is 3 minutes", dwc)
        self.assertIn("manual checkpoint when no async mechanism is available", e2e)

    def test_chatgpt_scheduled_tasks_require_actual_next_run(self) -> None:
        agents = self.normalized_text("AGENTS.md")
        chatgpt = self.normalized_text("agents/chatgpt-agent/agent-instructions.md")
        e2e = self.normalized_text("core/E2E_DRAFT_PR_DELIVERY_RULE.md")

        self.assertIn("ChatGPT Scheduled Tasks", chatgpt)
        self.assertIn("This is a scheduled continuation, not raw process sleep.", chatgpt)
        self.assertIn("If the UI shows no next run or a state such as `Chưa lên lịch`", chatgpt)
        self.assertIn("including `Chưa lên lịch`", agents)
        self.assertIn("The task is not active unless a concrete next run is visible or recorded.", e2e)

    def test_ci_failure_repair_invalidates_stale_g4_evidence(self) -> None:
        gate_contract = self.normalized_text("core/GATE_LIFECYCLE_CONTRACT_v1.0.md")
        agents = self.normalized_text("AGENTS.md")
        dwc = self.normalized_text("agents/dwc/agent-instructions.md")
        e2e = self.normalized_text("core/E2E_DRAFT_PR_DELIVERY_RULE.md")

        self.assertIn("repository-fixable failures within the active G2 scope", gate_contract)
        self.assertIn("Any repair commit invalidates prior CI", agents)
        self.assertIn("prior CI, review, and G4-readiness evidence as stale", dwc)
        self.assertIn("G4 approval may be generated only after required checks pass for the latest head SHA", gate_contract)
        self.assertIn("Invalidate prior CI, review, and G4-readiness evidence", e2e)


if __name__ == "__main__":
    unittest.main()
