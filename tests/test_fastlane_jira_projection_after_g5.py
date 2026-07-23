from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
E2E_RULE = ROOT / "core/E2E_DRAFT_PR_DELIVERY_RULE.md"
CONSUMER_INSTRUCTIONS = ROOT / "docs/project-consumer-agent-instructions.md"


class FastLaneJiraProjectionAfterG5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.e2e_text = E2E_RULE.read_text(encoding="utf-8")
        cls.consumer_text = CONSUMER_INSTRUCTIONS.read_text(encoding="utf-8")

    def test_e2e_rule_requires_work_tracking_projection_after_g5_pass(self) -> None:
        required_phrases = [
            "Work-tracking projection after G5 PASS",
            "After read-only `G5_STATUS_VERIFY` reaches `PASS`",
            "Add or update an audit comment",
            "Apply the legal provider transition",
            "Read back the provider task status",
            "Record the readback in the G5 outcome or final delivery report",
        ]
        for phrase in required_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.e2e_text)

    def test_e2e_rule_fails_honestly_when_jira_projection_is_blocked(self) -> None:
        required_phrases = [
            "JIRA_UPDATE_BLOCKED",
            "attempted provider",
            "task key",
            "intended transition",
            "late-reconciliation note",
            "must not backdate",
        ]
        for phrase in required_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.e2e_text)

    def test_external_work_tracking_never_grants_gwc_authority(self) -> None:
        for phrase in [
            "traceability only",
            "never grants repository write",
            "GWC gate artifacts and exact approvals remain the authority source",
        ]:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.e2e_text)

    def test_consumer_instructions_project_the_rule_to_project_agents(self) -> None:
        required_phrases = [
            "After read-only G5 status verification passes",
            "active work-tracking provider",
            "audit comment",
            "legal provider transition",
            "read back status/comment/update evidence",
            "JIRA_UPDATE_BLOCKED",
        ]
        for phrase in required_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.consumer_text)


if __name__ == "__main__":
    unittest.main()
