from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
G4 = (ROOT / ".github/workflows/g4-g5-evidence.yml").read_text(encoding="utf-8")
AUTO = (ROOT / ".github/workflows/autonomous-preprod-runtime.yml").read_text(encoding="utf-8")
ROUTE = "AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN"
PARENT = "gwc:autonomous-preprod-run-authority-receipt"


class AutonomousPreprodG4RoutingContractTests(unittest.TestCase):
    def test_legacy_g4_required_check_requires_trusted_parent_authority(self):
        self.assertIn("const autonomousPreprod =", G4)
        self.assertIn("pr.base.ref === 'pre-prod'", G4)
        self.assertIn("pr.head.ref.startsWith('auto/')", G4)
        self.assertIn(ROUTE, G4)
        self.assertIn(PARENT, G4)
        self.assertIn("AUTONOMOUS_RUN_AUTHORITY_UNTRUSTED", G4)

    def test_legacy_merge_proof_does_not_treat_route_marker_as_authority(self):
        self.assertNotIn("Standing pre-prod authority applies: human G4 receipt is not required", G4)
        self.assertIn(PARENT, G4)

    def test_autonomous_required_check_requires_parent_receipt_and_task_binding(self):
        self.assertIn("const standingPreprod =", AUTO)
        self.assertIn(PARENT, AUTO)
        self.assertIn("AUTONOMOUS_TASK_NOT_ALLOWLISTED", AUTO)
        self.assertIn("AUTONOMOUS_RUN_AUTHORITY_UNTRUSTED", AUTO)
        self.assertIn(ROUTE, AUTO)

    def test_route_marker_alone_is_not_standing_authority(self):
        self.assertNotIn(
            "auto/* -> pre-prod is authorized by AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN standing policy",
            AUTO,
        )

    def test_human_g4_boundary_for_main_is_preserved(self):
        self.assertIn("gwc:g4-authority-receipt", G4)
        self.assertIn("Human G4 remains mandatory for promotion to main", G4)
        self.assertIn("human G4 is reserved for promotion to main", AUTO)


if __name__ == "__main__":
    unittest.main()
