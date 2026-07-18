from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "gwc-g3" / "SKILL.md"


class G3SkillContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SKILL.read_text(encoding="utf-8")

    def test_stage_contract_is_present(self) -> None:
        for marker in ("G3.1 PR Assembly", "G3.2 Independent Review", "G3.3 Review Closure"):
            self.assertIn(marker, self.text)

    def test_context7_first_offline_fallback_is_explicit(self) -> None:
        for marker in ("/obra/superpowers", "Context7 is attempted before", "OFFLINE_PINNED", "bundle-atomic", "G3_SKILL_SOURCE_BLOCKED"):
            self.assertIn(marker, self.text)

    def test_required_skill_composition_is_explicit(self) -> None:
        for marker in ("requesting-code-review", "verification-before-completion", "receiving-code-review", "finishing-development-branch-pr-only", "dispatching-parallel-review"):
            self.assertIn(marker, self.text)

    def test_exact_evidence_and_boundaries_are_present(self) -> None:
        for marker in ("exact current head SHA", "scope hash", "read-only", "tools/validate_g3_delivery.py", "Do not merge"):
            self.assertIn(marker, self.text)


if __name__ == "__main__":
    unittest.main()
