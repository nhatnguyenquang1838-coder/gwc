from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RoutePrecedenceContractTests(unittest.TestCase):
    def read(self, path: str) -> str:
        return (ROOT / path).read_text(encoding="utf-8")

    def test_agents_resolves_route_before_generic_workflow(self):
        text = self.read("AGENTS.md")
        self.assertIn("ROUTE_RESOLUTION_PRECEDES_GENERIC_WORKFLOW", text)
        self.assertIn("AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN", text)
        self.assertIn("valid exact-head standing G4", text)
        self.assertIn("Human G4 remains mandatory for every `pre-prod -> main`", text)
        self.assertLess(
            text.index("core/AUTONOMOUS_PREPROD_INTEGRATION_POLICY_v1.0.md"),
            text.index("core/GATE_LIFECYCLE_CONTRACT_v1.0.md"),
        )

    def test_e2e_is_mechanics_not_g4_authority_source(self):
        text = self.read("core/E2E_DRAFT_PR_DELIVERY_RULE.md")
        self.assertIn("ROUTE_RESOLUTION_PRECEDES_GENERIC_WORKFLOW", text)
        self.assertIn("E2E defines delivery\nmechanics", text)
        self.assertIn("auto/* -> pre-prod", text)
        self.assertIn("pre-prod -> main requires Human G4", text)
        self.assertNotIn(
            "G4 remains a separate human decision for the exact PR head SHA.",
            text,
        )

    def test_project_extension_does_not_force_human_g4_for_autonomous_child(self):
        text = self.read("projects/gwc/project-extension.md")
        self.assertIn("Route-specific authority precedence", text)
        self.assertIn("valid exact-head standing G4", text)
        self.assertIn("Human G4 remains\n  mandatory for every `pre-prod -> main`", text)
        self.assertNotIn(
            "G4 merge, G5 deploy, and G6 production operations always remain human gates.",
            text,
        )


if __name__ == "__main__":
    unittest.main()
