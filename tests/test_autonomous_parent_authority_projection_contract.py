from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MATERIALIZER = (ROOT / ".github/workflows/autonomous-parent-authority-materializer.yml").read_text(encoding="utf-8")
RUNTIME = (ROOT / ".github/workflows/autonomous-preprod-runtime.yml").read_text(encoding="utf-8")


class AutonomousParentAuthorityProjectionContractTests(unittest.TestCase):
    def test_materializer_emits_identity_fields_required_by_runtime(self):
        required_projection_fragments = (
            "status=${receipt.status}",
            "source=${receipt.source}",
            "bot_login=${receipt.bot_login}",
            "marker=${receipt.marker}",
        )
        for fragment in required_projection_fragments:
            self.assertIn(fragment, MATERIALIZER)

        required_runtime_checks = (
            "parentReceipt.status === 'present'",
            "parentReceipt.source === 'github_actions_bot_comment'",
            "parentReceipt.bot_login === 'github-actions[bot]'",
            "parentReceipt.marker === parentReceiptMarker",
        )
        for fragment in required_runtime_checks:
            self.assertIn(fragment, RUNTIME)

    def test_materializer_readback_verifies_identity_fields(self):
        for fragment in (
            "status=${receipt.status} ",
            "source=${receipt.source} ",
            "bot_login=${receipt.bot_login} ",
            "marker=${receipt.marker} ",
        ):
            self.assertIn(fragment, MATERIALIZER)


if __name__ == "__main__":
    unittest.main()
