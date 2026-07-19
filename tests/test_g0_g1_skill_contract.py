from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
G0_SKILL = ROOT / "skills" / "gwc-g0" / "SKILL.md"
G1_SKILL = ROOT / "skills" / "gwc-g1" / "SKILL.md"


class G0G1SkillContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.g0_text = G0_SKILL.read_text(encoding="utf-8")
        cls.g1_text = G1_SKILL.read_text(encoding="utf-8")

    def test_g0_context7_first_offline_fallback_is_explicit(self) -> None:
        for marker in (
            "/obra/superpowers",
            "Context7 is attempted before",
            "OFFLINE_PINNED",
            "bundle-atomic",
            "G0_G1_SKILL_SOURCE_BLOCKED",
        ):
            self.assertIn(marker, self.g0_text)

    def test_g0_required_skill_composition_is_explicit(self) -> None:
        self.assertIn("g0-context-loading", self.g0_text)

    def test_g0_exact_evidence_and_boundaries_are_present(self) -> None:
        for marker in (
            "A `READY` G0 snapshot means context is usable",
            "G0_CONTEXT_BLOCKED",
            "NO_EXECUTION_AUTHORITY_GRANTED",
            "UNVERIFIED_BY_TOOL",
        ):
            self.assertIn(marker, self.g0_text)

    def test_g1_context7_first_offline_fallback_is_explicit(self) -> None:
        for marker in (
            "/obra/superpowers",
            "Context7 is attempted before",
            "OFFLINE_PINNED",
            "bundle-atomic",
            "G0_G1_SKILL_SOURCE_BLOCKED",
        ):
            self.assertIn(marker, self.g1_text)

    def test_g1_required_skill_composition_is_explicit(self) -> None:
        for marker in (
            "g1-intake-options-preflight",
            "g1-decision-record",
            "g0-g1-approval-envelope",
        ):
            self.assertIn(marker, self.g1_text)

    def test_g1_exact_evidence_and_boundaries_are_present(self) -> None:
        for marker in (
            "G2_EXECUTION_NOT_GRANTED",
            "G1_DECISION_ACCEPTED_FOR_G2_PLANNING",
            "authority_boundaries",
            "G4_MERGE",
            "G5_DEPLOY",
            "G6_PRODUCTION",
        ):
            self.assertIn(marker, self.g1_text)


if __name__ == "__main__":
    unittest.main()