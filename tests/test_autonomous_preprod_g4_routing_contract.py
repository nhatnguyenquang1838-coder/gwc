from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
G4 = (ROOT / ".github/workflows/g4-g5-evidence.yml").read_text(encoding="utf-8")
AUTO = (ROOT / ".github/workflows/autonomous-preprod-runtime.yml").read_text(encoding="utf-8")
MATERIALIZER = (ROOT / ".github/workflows/autonomous-parent-authority-materializer.yml").read_text(encoding="utf-8")
PARENT_REQUIRED = (ROOT / ".github/workflows/autonomous-parent-authority-required.yml").read_text(encoding="utf-8")
ROUTE = "AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN"
PARENT = "gwc:autonomous-preprod-run-authority-receipt"


class AutonomousPreprodG4RoutingContractTests(unittest.TestCase):
    def test_legacy_g4_check_is_not_sufficient_standing_authority_evidence(self):
        self.assertIn("const autonomousPreprod =", G4)
        self.assertIn("pr.base.ref === 'pre-prod'", G4)
        self.assertIn("pr.head.ref.startsWith('auto/')", G4)
        self.assertIn(ROUTE, G4)
        self.assertIn("Human G4 remains mandatory for promotion to main", G4)
        self.assertIn("parent-authority-required:", PARENT_REQUIRED)

    def test_autonomous_required_check_requires_trusted_parent_receipt(self):
        self.assertIn(PARENT, PARENT_REQUIRED)
        self.assertIn("AUTONOMOUS_RUN_AUTHORITY_UNTRUSTED", PARENT_REQUIRED)
        self.assertIn("AUTONOMOUS_TASK_NOT_ALLOWLISTED", PARENT_REQUIRED)
        self.assertIn("parentAuthorityIssue", PARENT_REQUIRED)
        self.assertIn(ROUTE, PARENT_REQUIRED)

    def test_route_marker_alone_is_not_standing_authority(self):
        self.assertIn("exactly one gwc:autonomous-parent-authority marker is required", PARENT_REQUIRED)
        self.assertIn("trusted github-actions[bot] parent authority receipt is missing", PARENT_REQUIRED)
        self.assertIn("trusted parent manifest projection is missing", PARENT_REQUIRED)

    def test_parent_authority_issuer_is_human_source_plus_bot_receipt(self):
        self.assertIn("APPROVE AUTONOMOUS_RUN", MATERIALIZER)
        self.assertIn("github-actions[bot]", MATERIALIZER)
        self.assertIn("source_comment_id", MATERIALIZER)
        self.assertIn("manifest_comment_id", MATERIALIZER)
        self.assertIn("manifest_scope_digest", MATERIALIZER)
        self.assertIn("getCollaboratorPermissionLevel", PARENT_REQUIRED)

    def test_parent_authority_is_materialized_before_child_claim(self):
        self.assertIn("name: Autonomous parent authority materializer", MATERIALIZER)
        self.assertIn("startsWith(github.event.comment.body, 'APPROVE AUTONOMOUS_RUN ')", MATERIALIZER)
        self.assertIn("AUTONOMOUS_RUN_AUTHORITY_READBACK_MISMATCH", MATERIALIZER)
        self.assertIn("name: Autonomous parent authority required", PARENT_REQUIRED)
        self.assertIn("pull_request:", PARENT_REQUIRED)

    def test_parent_authority_consumer_can_follow_explicit_parent_issue(self):
        self.assertIn("gwc:autonomous-parent-authority issue=", PARENT_REQUIRED)
        self.assertIn("parentAuthorityIssue", PARENT_REQUIRED)
        self.assertIn("expectedRunId", PARENT_REQUIRED)
        self.assertIn("projectedReceipt.approved_run_id !== expectedRunId", PARENT_REQUIRED)
        self.assertIn("task.working_branch !== pr.head.ref", PARENT_REQUIRED)

    def test_human_g4_boundary_for_main_is_preserved(self):
        self.assertIn("gwc:g4-authority-receipt", G4)
        self.assertIn("Human G4 remains mandatory for promotion to main", G4)
        self.assertIn("human G4 is reserved for promotion to main", AUTO)


if __name__ == "__main__":
    unittest.main()
