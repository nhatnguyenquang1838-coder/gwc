"""Regression tests for consolidated gate lifecycle process rules."""

from pathlib import Path
import unittest

from helpers.chatgpt_instruction_composer import (
    ChatGPTInstructionCompositionError,
    compose_chatgpt_instructions,
    resolve_base_edge,
)


ROOT = Path(__file__).resolve().parents[1]


class GateLifecycleProcessContractTests(unittest.TestCase):
    def read_text(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def normalized_text(self, relative_path: str) -> str:
        return " ".join(self.read_text(relative_path).split())

    @classmethod
    def setUpClass(cls):
        # The ChatGPT agent instructions are a Composed Entrypoint: the thin
        # composer delegates the full instruction set to gwc-governed-base.md.
        # Validate the composed effective instructions (SCRUM-404 / #441).
        cls.chatgpt = compose_chatgpt_instructions(ROOT)

    def test_g5_is_status_check_when_cicd_handles_deployment(self) -> None:
        gate_contract = self.normalized_text("core/GATE_LIFECYCLE_CONTRACT_v1.0.md")
        agents = self.normalized_text("AGENTS.md")
        dwc = self.normalized_text("agents/dwc/agent-instructions.md")
        chatgpt = self.chatgpt
        e2e = self.normalized_text("core/E2E_DRAFT_PR_DELIVERY_RULE.md")

        self.assertIn("When deployment is already automated by CI/CD, G5 is status verification only.", gate_contract)
        self.assertIn("G5 is a status/deployment verification gate.", agents)
        self.assertIn("G5 is status/deployment verification.", dwc)
        self.assertIn("For G5, do not infer a manual deploy/reload from the gate name.", chatgpt)
        self.assertIn("G5 checks those workflow/deployment statuses", e2e)
        self.assertIn("Read-only `G5_STATUS_VERIFY` starts automatically", gate_contract)
        self.assertIn("read-only `G5_STATUS_VERIFY` runs automatically after G4 merge", e2e)

    def test_composed_entrypoint_requires_exactly_one_base_edge(self) -> None:
        entrypoint = "`agents/chatgpt-agent/gwc-governed-base.md`\n"
        self.assertEqual(
            resolve_base_edge(entrypoint),
            "agents/chatgpt-agent/gwc-governed-base.md",
        )
        with self.assertRaises(ChatGPTInstructionCompositionError):
            resolve_base_edge(entrypoint + entrypoint)

    def test_ready_for_review_is_g3_metadata_completion(self) -> None:
        gate_contract = self.normalized_text("core/GATE_LIFECYCLE_CONTRACT_v1.0.md")
        agents = self.normalized_text("AGENTS.md")
        dwc = self.normalized_text("agents/dwc/agent-instructions.md")
        chatgpt = self.chatgpt
        e2e = self.normalized_text("core/E2E_DRAFT_PR_DELIVERY_RULE.md")

        self.assertIn("Mark Draft PR ready for review after G3 `PASS`", gate_contract)
        self.assertIn("github_mark_pr_ready_for_review", dwc)
        self.assertIn("This transition is not merge approval", chatgpt)
        self.assertIn("G3 review decision does not authorize merge", e2e)
        self.assertIn("This ready-for-review transition is G3 metadata completion", agents)

    def test_chatgpt_gwc_responses_are_vietnamese_first(self) -> None:
        agents = self.normalized_text("AGENTS.md")
        chatgpt = self.chatgpt

        self.assertIn("ChatGPT-style agents operating in GWC project chat must respond Vietnamese-first", agents)
        self.assertIn("Status reports, blockers, evidence summaries, recommendations, and next actions should be written primarily in Vietnamese", chatgpt)

    def test_g6_is_not_generated_without_production_operation_scope(self) -> None:
        gate_contract = self.normalized_text("core/GATE_LIFECYCLE_CONTRACT_v1.0.md")
        agents = self.normalized_text("AGENTS.md")
        dwc = self.normalized_text("agents/dwc/agent-instructions.md")
        chatgpt = self.chatgpt

        expected = "G6 is generated only when production data, production configuration, migration, credential, or secret operations are actually in scope."
        self.assertIn(expected, agents)
        self.assertIn("generate a G6 approval request only when", gate_contract)
        self.assertIn("production data, production configuration, migrations, credentials, or secrets", dwc)
        self.assertIn("record `not_applicable`", chatgpt)

    def test_work_tracking_sync_and_late_reconciliation_are_required(self) -> None:
        gate_contract = self.normalized_text("core/GATE_LIFECYCLE_CONTRACT_v1.0.md")
        agents = self.normalized_text("AGENTS.md")
        dwc = self.normalized_text("agents/dwc/agent-instructions.md")
        chatgpt = self.chatgpt

        self.assertIn("Update the active work-tracking task through its legal provider transition", gate_contract)
        self.assertIn("The agent must synchronize the active work-tracking provider before continuing", agents)
        self.assertIn("## Work-tracking state synchronization", dwc)
        self.assertIn("late reconciliation must be disclosed as late", chatgpt)

    def test_gwc_uses_direct_jira_mcp_for_new_tasks(self) -> None:
        profile = self.normalized_text("projects/gwc/project-profile.yaml")
        package = self.normalized_text("projects/gwc/package.yaml")
        instructions = self.normalized_text("projects/gwc/project-instructions.md")
        extension = self.normalized_text("projects/gwc/project-extension.md")

        self.assertIn("api_connector: Atlassian Jira MCP", profile)
        self.assertIn("provider: jira-mcp", package)
        self.assertIn("status_transitions_from_state_engine: false", package)
        self.assertIn("Jira MCP is the work-tracking source of truth for new GWC tasks", profile)
        self.assertIn("Jira via Atlassian MCP", instructions)
        self.assertIn("Every new modifying task must have exactly one Jira issue", extension)
        self.assertIn("Existing DS Admin and Rental Home task records remain unchanged", extension)

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
        chatgpt = self.chatgpt

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

    def test_chatgpt_ci_continuation_sleeps_the_current_thread(self) -> None:
        agents = self.normalized_text("AGENTS.md")
        chatgpt = self.chatgpt
        e2e = self.normalized_text("core/E2E_DRAFT_PR_DELIVERY_RULE.md")

        self.assertIn("two-minute sleep of the active thread", agents)
        self.assertIn("sleep the current thread for exactly two minutes", chatgpt)
        self.assertIn("Do not create a scheduler task or automation", chatgpt)
        self.assertIn("two-minute sleep of the active thread", e2e)
        self.assertIn("For other platform schedulers", e2e)
        self.assertNotIn("## ChatGPT Scheduled Tasks", chatgpt)
        self.assertNotIn("3-minute next-check interval", chatgpt)

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

    def test_g5_post_merge_verification_requires_exact_sha_lookup(self) -> None:
        gate_contract = self.normalized_text("core/GATE_LIFECYCLE_CONTRACT_v1.0.md")
        agents = self.normalized_text("AGENTS.md")
        dwc = self.normalized_text("agents/dwc/agent-instructions.md")
        chatgpt = self.chatgpt
        e2e = self.normalized_text("core/E2E_DRAFT_PR_DELIVERY_RULE.md")

        expected = "event=push"
        self.assertIn(expected, gate_contract)
        self.assertIn("head_sha=<merge_sha>", gate_contract)
        self.assertIn("CONNECTOR_OBSERVABILITY_INCOMPLETE", gate_contract)

        self.assertIn("exact post-merge lookup", agents)
        self.assertIn("CONNECTOR_OBSERVABILITY_INCOMPLETE", agents)
        self.assertIn("`CI_PENDING` is reserved only when", agents)

        self.assertIn("event=push", dwc)
        self.assertIn("head_sha=<merge_sha>", dwc)
        self.assertIn("CONNECTOR_OBSERVABILITY_INCOMPLETE", dwc)

        self.assertIn("event=push", chatgpt)
        self.assertIn("head_sha=<merge_sha>", chatgpt)
        self.assertIn("CONNECTOR_OBSERVABILITY_INCOMPLETE", chatgpt)

        self.assertIn("event=push", e2e)
        self.assertIn("CONNECTOR_OBSERVABILITY_INCOMPLETE", e2e)


if __name__ == "__main__":
    unittest.main()
