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
            "projectedReceipt.status !== 'present'",
            "projectedReceipt.source !== 'github_actions_bot_comment'",
            "projectedReceipt.bot_login !== 'github-actions[bot]'",
            "projectedReceipt.marker !== receiptMarker",
            "projectedReceipt.approved_run_id !== expectedRunId",
            "projectedReceipt.manifest_scope_digest !== parentReceipt.manifest_scope_digest",
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

    def test_consumer_supports_legacy_marker_without_weakening_manifest_identity(self):
        self.assertIn("Legacy R3B receipt comments predate explicit status/source/bot_login/marker", CONSUMER)
        self.assertIn("item.user?.login === 'github-actions[bot]'", CONSUMER)
        self.assertIn("projectedReceipt.approval_id !== parentReceipt.approval_id", CONSUMER)
        self.assertIn("projectedReceipt.receipt_comment_id", CONSUMER)
        self.assertIn("projectedReceipt.source_comment_id", CONSUMER)

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
