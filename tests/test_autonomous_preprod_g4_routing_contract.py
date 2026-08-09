from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
G4 = (ROOT / ".github/workflows/g4-g5-evidence.yml").read_text(encoding="utf-8")
AUTO = (ROOT / ".github/workflows/autonomous-preprod-runtime.yml").read_text(encoding="utf-8")
ROUTE = "AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN"


class AutonomousPreprodG4RoutingContractTests(unittest.TestCase):
    def test_legacy_g4_required_check_recognizes_standing_preprod_authority(self):
        self.assertIn("const autonomousPreprod =", G4)
        self.assertIn("pr.base.ref === 'pre-prod'", G4)
        self.assertIn("pr.head.ref.startsWith('auto/')", G4)
        self.assertIn(ROUTE, G4)
        self.assertIn("Standing pre-prod authority applies", G4)

    def test_legacy_merge_proof_does_not_require_human_g4_for_autonomous_preprod_merge(self):
        self.assertIn("!(github.event.pull_request.base.ref == 'pre-prod'", G4)
        self.assertIn("startsWith(github.event.pull_request.head.ref, 'auto/')", G4)
        self.assertIn(ROUTE, G4)

    def test_autonomous_required_check_passes_under_standing_preprod_authority(self):
        self.assertIn("const standingPreprod =", AUTO)
        self.assertIn("Autonomous pre-prod standing authority applies", AUTO)
        self.assertIn(ROUTE, AUTO)

    def test_human_g4_boundary_for_main_is_preserved(self):
        self.assertIn("gwc:g4-authority-receipt", G4)
        self.assertIn("Human G4 remains mandatory for promotion to main", G4)
        self.assertIn("human G4 is reserved for promotion to main", AUTO)


if __name__ == "__main__":
    unittest.main()
