from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
ROOT_INSTRUCTIONS = ROOT / "AGENTS.md"
INSTRUCTIONS = ROOT / "agents/chatgpt-agent/agent-instructions.md"
PACKAGE = ROOT / "projects/gwc/package.yaml"
KIRO_RULE = ROOT / "core/KIRO_SPEC_DRIVEN_DELIVERY_RULE_v1.0.md"
TASK_WORKSPACE = ROOT / ".gwc/tasks/task_73fadcb1-c2db-4f6f-856c-a98eb778ec23"


class ChatGPTArtifactContinuationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root_text = ROOT_INSTRUCTIONS.read_text(encoding="utf-8")
        cls.text = INSTRUCTIONS.read_text(encoding="utf-8")
        cls.package = yaml.safe_load(PACKAGE.read_text(encoding="utf-8"))
        cls.kiro_text = KIRO_RULE.read_text(encoding="utf-8")

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

    def test_package_distributes_runbook_and_kiro_rule(self) -> None:
        self.assertEqual(self.package["package_version"], "1.16.0")
        entries = {item["id"]: item for item in self.package["instructions"]}
        self.assertIn("g0-g1-operational-runbook", entries)
        self.assertEqual(
            entries["g0-g1-operational-runbook"]["path"],
            "core/runbooks/GATE_G0_G1_OPERATIONAL_RUNBOOK_v1.0.md",
        )
        self.assertTrue(entries["g0-g1-operational-runbook"]["required"])
        self.assertIn("kiro-spec-driven-delivery-rule", entries)
        self.assertEqual(
            entries["kiro-spec-driven-delivery-rule"]["path"],
            "core/KIRO_SPEC_DRIVEN_DELIVERY_RULE_v1.0.md",
        )
        self.assertTrue(entries["kiro-spec-driven-delivery-rule"]["required"])

    def test_kiro_rule_requires_chatgpt_task_runtime_parity(self) -> None:
        required_phrases = [
            "resolve or create exactly one AgentOps/DS Admin task",
            ".gwc/tasks/<task-id>/",
            "Repository persistence of `.gwc` artifacts is itself a G2 write",
            "do not grant repository write",
        ]
        for phrase in required_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.kiro_text)

        required_artifacts = [
            "g0/context-snapshot.yaml",
            "g1/intake/g1-intake-brief.yaml",
            "g1/preflight/g1-preflight-report.yaml",
            "g1/brainstorming/g1-options.yaml",
            "g1/decision/g1-decision-record.yaml",
            "g2/execution-envelope.yaml",
            "g2/ci-repair-envelope-01.yaml",
        ]
        for relative_path in required_artifacts:
            with self.subTest(relative_path=relative_path):
                self.assertTrue((TASK_WORKSPACE / relative_path).is_file())


if __name__ == "__main__":
    unittest.main()
