from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
G4 = (ROOT / ".github/workflows/g4-g5-evidence.yml").read_text(encoding="utf-8")
AUTO = (ROOT / ".github/workflows/autonomous-preprod-runtime.yml").read_text(encoding="utf-8")
ROUTE = "AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN"
PARENT = "gwc:autonomous-preprod-run-authority-receipt"


class AutonomousPreprodG4RoutingContractTests(unittest.TestCase):
    def test_legacy_g4_check_is_not_sufficient_standing_authority_evidence(self):
        self.assertIn("const autonomousPreprod =", G4)
        self.assertIn("pr.base.ref === 'pre-prod'", G4)
        self.assertIn("pr.head.ref.startsWith('auto/')", G4)
        self.assertIn(ROUTE, G4)
        self.assertIn("Human G4 remains mandatory for promotion to main", G4)

    def test_autonomous_required_check_requires_trusted_parent_receipt(self):
        self.assertIn("const standingPreprod =", AUTO)
        self.assertIn(PARENT, AUTO)
        self.assertIn("AUTONOMOUS_RUN_AUTHORITY_UNTRUSTED", AUTO)
        self.assertIn("AUTONOMOUS_TASK_NOT_ALLOWLISTED", AUTO)
        self.assertIn("parentAuthorityIssue", AUTO)
        self.assertIn(ROUTE, AUTO)

    def test_route_marker_alone_is_not_standing_authority(self):
        self.assertNotIn(
            "auto/* -> pre-prod is authorized by AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN standing policy",
            AUTO,
        )

    def test_parent_authority_issuer_is_human_source_plus_bot_receipt(self):
        self.assertIn("APPROVE AUTONOMOUS_RUN", AUTO)
        self.assertIn("github-actions[bot]", AUTO)
        self.assertIn("source_comment_id", AUTO)
        self.assertIn("manifest_comment_id", AUTO)
        self.assertIn("manifest_scope_digest", AUTO)

    def test_parent_authority_is_materialized_before_child_claim(self):
        self.assertIn("parent-run-authority-materializer:", AUTO)
        self.assertIn("materialize_parent_authority:", AUTO)
        self.assertIn("authority_source_issue_number:", AUTO)
        self.assertIn("authority_source_comment_id:", AUTO)
        self.assertIn("authority_manifest_json:", AUTO)
        self.assertIn("autonomous-parent-authority-materialized", AUTO)
        self.assertIn("AUTONOMOUS_RUN_AUTHORITY_READBACK_MISMATCH", AUTO)
        self.assertIn("!inputs.materialize_parent_authority", AUTO)

    def test_parent_authority_consumer_can_follow_explicit_parent_issue(self):
        self.assertIn("gwc:autonomous-parent-authority issue=", AUTO)
        self.assertIn("authorityIssueNumber", AUTO)
        self.assertIn("expectedRunId", AUTO)
        self.assertIn("parentReceipt.approved_run_id === expectedRunId", AUTO)

    def test_human_g4_boundary_for_main_is_preserved(self):
        self.assertIn("gwc:g4-authority-receipt", G4)
        self.assertIn("Human G4 remains mandatory for promotion to main", G4)
        self.assertIn("human G4 is reserved for promotion to main", AUTO)


if __name__ == "__main__":
    unittest.main()
