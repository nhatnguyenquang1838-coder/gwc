from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MATERIALIZER = (ROOT / ".github/workflows/autonomous-parent-authority-materializer.yml").read_text(encoding="utf-8")
CONSUMER = (ROOT / ".github/workflows/autonomous-parent-authority-required.yml").read_text(encoding="utf-8")


class AutonomousParentAuthorityProjectionContractTests(unittest.TestCase):
    def test_materializer_emits_identity_fields_required_by_consumer(self):
        for fragment in (
            "status=${receipt.status}",
            "source=${receipt.source}",
            "bot_login=${receipt.bot_login}",
            "marker=${receipt.marker}",
        ):
            self.assertIn(fragment, MATERIALIZER)

        for fragment in (
            "parentReceipt.status !== 'present'",
            "parentReceipt.source !== 'github_actions_bot_comment'",
            "parentReceipt.bot_login !== 'github-actions[bot]'",
            "parentReceipt.marker !== receiptMarker",
            "projectedReceipt.status !== 'present'",
            "projectedReceipt.approved_run_id !== expectedRunId",
        ):
            self.assertIn(fragment, CONSUMER)

    def test_materializer_readback_verifies_identity_fields(self):
        for fragment in (
            "status=${receipt.status} ",
            "source=${receipt.source} ",
            "bot_login=${receipt.bot_login} ",
            "marker=${receipt.marker} ",
        ):
            self.assertIn(fragment, MATERIALIZER)

    def test_consumer_requires_human_source_and_machine_policy_continuity(self):
        for fragment in (
            "APPROVE AUTONOMOUS_RUN",
            "getCollaboratorPermissionLevel",
            "AUTONOMOUS_AUTHORITY_POLICY_DRIFT",
            "compareCommitsWithBasehead",
            "governance/autonomous-preprod-policy.yaml",
        ):
            self.assertIn(fragment, CONSUMER)


if __name__ == "__main__":
    unittest.main()
