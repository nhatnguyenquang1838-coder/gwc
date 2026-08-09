from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ChatConnectorRuntimeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        cls.runtime = (ROOT / "core/Agent_Operating_Runtime_Contract_v1.0.md").read_text(encoding="utf-8")
        cls.chatgpt = (ROOT / "agents/chatgpt-agent/agent-instructions.md").read_text(encoding="utf-8")
        cls.runbook = (ROOT / "core/runbooks/GATE_G0_G1_OPERATIONAL_RUNBOOK_v1.0.md").read_text(encoding="utf-8")

    def test_execution_mode_depends_on_trusted_checkout_not_validator_runner(self):
        self.assertIn("Validator availability does not determine execution mode", self.agents)
        self.assertIn("even if an isolated filesystem and\n  command runner can validate fetched artifacts", self.chatgpt)
        self.assertIn("Connector-only does not mean validator-unavailable", self.runbook)

    def test_connector_content_plus_writable_workspace_is_materialization_capable(self):
        self.assertIn(
            "A connector that returns exact file content/text/blob data plus a writable\nisolated filesystem is sufficient for materialization",
            self.agents,
        )
        self.assertIn("mounted connector file is\n   not required", self.runtime)

    def test_connector_only_can_write_after_valid_gate_authority(self):
        self.assertIn("use an authorized repository write connector for guarded-branch creation", self.agents)
        self.assertIn("A trusted checkout is NOT required to use an authorized repository write connector", self.runtime)
        self.assertIn("Persisting those artifacts to the repository remains a G2 write", self.chatgpt)

    def test_autonomous_route_uses_derived_g2_and_standing_g4_for_preprod_only(self):
        self.assertIn("AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN", self.agents)
        self.assertIn("derived child G2", self.runtime)
        self.assertIn("exact-head standing G4 for auto/* → pre-prod", self.runtime)
        self.assertIn("Human G4 for pre-prod → main", self.runtime)
        self.assertIn("Standing authority never authorizes merge to `main`", self.agents)

    def test_route_execution_base_overrides_generic_default_branch(self):
        self.assertIn("route-specific execution base `pre-prod` overrides a generic default-branch", self.agents)
        self.assertIn("`pre-prod` is the autonomous child execution/integration base", self.runtime)
        self.assertIn("`main` remains governance/release/promotion context", self.runtime)

    def test_missing_capability_blocks_only_required_action(self):
        self.assertIn("Missing one capability blocks only actions that require that capability", self.runtime)
        self.assertIn("Do not collapse capability absence into a generic execution-mode blocker", self.runtime)


if __name__ == "__main__":
    unittest.main()
