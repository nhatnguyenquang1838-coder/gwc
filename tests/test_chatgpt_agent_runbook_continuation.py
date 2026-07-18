from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
ROOT_INSTRUCTIONS = ROOT / "AGENTS.md"
INSTRUCTIONS = ROOT / "agents/chatgpt-agent/agent-instructions.md"
PACKAGE = ROOT / "projects/gwc/package.yaml"


class ChatGPTArtifactContinuationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root_text = ROOT_INSTRUCTIONS.read_text(encoding="utf-8")
        cls.text = INSTRUCTIONS.read_text(encoding="utf-8")
        cls.package = yaml.safe_load(PACKAGE.read_text(encoding="utf-8"))

    def test_root_routes_by_capability_without_identity_else_branch(self) -> None:
        self.assertIn("## Agent-specific routing", self.root_text)
        self.assertIn("Select execution mode from verified capabilities", self.root_text)
        self.assertIn("ChatGPT-style agent with a trusted checkout", self.root_text)
        self.assertNotIn("ELSE for LOCAL AGENT", self.root_text)

    def test_chatgpt_overlay_is_additive_to_root_governance(self) -> None:
        self.assertIn("additive\nruntime overlay on the parent `AGENTS.md`", self.text)
        self.assertIn("parent file remains canonical", self.text)
        self.assertIn("Do not downgrade a capable ChatGPT agent", self.text)

    def test_connectors_use_fallback_instead_of_mandatory_onboarding(self) -> None:
        self.assertIn("GitHub, then DWC, then DW1", self.text)
        self.assertIn("Do not require onboarding every declared connector", self.text)
        self.assertNotIn("Onboard Github Connector", self.text)
        self.assertNotIn("FAILED LOADING", self.text)

    def test_runbook_is_mandatory_boot_source(self) -> None:
        self.assertIn(
            "core/runbooks/GATE_G0_G1_OPERATIONAL_RUNBOOK_v1.0.md",
            self.text,
        )

    def test_connector_agent_recovers_artifacts_before_blocking(self) -> None:
        required = [
            "Pin and re-verify the protected-base SHA",
            "Fetch the required gate artifacts, schemas, templates, validators",
            "/mnt/data/gwc_sessions/<session-id>/",
            "Repair and retry remediable",
            "exact validator evidence unavailable after artifact recovery",
        ]
        for phrase in required:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.text)

    def test_all_gate_transitions_generate_next_artifact(self) -> None:
        for phrase in [
            "G1 PASS | G2 execution envelope plus approval request",
            "G2 PASS | G3 delivery record",
            "G3 PASS | G4 merge approval request",
            "G4 PASS | G5 deployment approval request",
            "G5 PASS | G6 production approval request",
        ]:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.text)

    def test_real_authority_boundaries_remain_hard_stops(self) -> None:
        for phrase in [
            "protected-branch write",
            "merge",
            "deployment",
            "production-data operation",
            "scope drift",
            "expired approval",
            "connector hard denial",
        ]:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.text)

    def test_package_distributes_runbook(self) -> None:
        self.assertEqual(self.package["package_version"], "1.12.0")
        entries = {item["id"]: item for item in self.package["instructions"]}
        self.assertIn("g0-g1-operational-runbook", entries)
        self.assertEqual(
            entries["g0-g1-operational-runbook"]["path"],
            "core/runbooks/GATE_G0_G1_OPERATIONAL_RUNBOOK_v1.0.md",
        )
        self.assertTrue(entries["g0-g1-operational-runbook"]["required"])


if __name__ == "__main__":
    unittest.main()
