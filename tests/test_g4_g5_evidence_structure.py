"""Structural regression tests for the G4/G5 evidence workflow and the
lane-integrity obligations added for SCRUM-260.

These tests fail closed when:
  * `g4-g5-evidence.yml` stops parsing as YAML;
  * a duplicate top-level job key is reintroduced (the historical
    duplicate `g5-recovery` regression);
  * the expected job set drifts;
  * the governed instruction surfaces lose the pre-write lane assertion,
    foreign-dirty-state, post-approval readback, fail-closed recovery, or
    exact-binding status obligations.
"""

from __future__ import annotations

from pathlib import Path
import unittest

import yaml

from helpers.chatgpt_instruction_composer import (
    compose_chatgpt_instructions,
)

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "g4-g5-evidence.yml"
CONTRACT = ROOT / "core" / "GATE_LIFECYCLE_CONTRACT_v1.0.md"
# The ChatGPT agent instructions are a Composed Entrypoint; validate the
# effective (composer + gwc-governed-base.md) content per SCRUM-404 / #441.
CHATGPT_INSTRUCTIONS = compose_chatgpt_instructions(ROOT)
INSTRUCTION_SURFACES = (
    CHATGPT_INSTRUCTIONS,
    ROOT / "agents" / "dwc" / "agent-instructions.md",
    ROOT / "agents" / "instructionops-agent" / "agent-instructions.md",
)

EXPECTED_JOBS = {"g4-authority", "g4-receipt-required", "g4-merge-proof", "g5-status", "g5-recovery"}

LANE_MARKERS = (
    "LANE ASSERTION",
    "LANE_ASSERTION_MISSING",
    "LANE_DRIFT_DETECTED",
    "FOREIGN DIRTY STATE",
    "FOREIGN_DIRTY_STATE_DETECTED",
    "gwc:g4-authority-receipt",
    "issue_comment",
    "G4_RECEIPT_MISSING",
    "APPROVE G5 RECOVERY",
    "RECOVERY_EVIDENCE_UNBOUND",
    "source_digest",
    "SHA_MISMATCH",
)


class _DuplicateKeyGuard(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys instead of silently
    keeping the last one (PyYAML's default, which hid the original bug)."""


def _no_duplicate_keys(loader: _DuplicateKeyGuard, node, deep: bool = False):
    mapping: dict = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"duplicate key: {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_DuplicateKeyGuard.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicate_keys
)


class G4G5EvidenceStructureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(WORKFLOW.is_file(), f"missing workflow: {WORKFLOW}")
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_workflow_parses_without_duplicate_keys(self) -> None:
        """Duplicate top-level job definitions (or any duplicate mapping key)
        must raise, not be silently collapsed."""
        document = yaml.load(self.text, Loader=_DuplicateKeyGuard)
        self.assertIsInstance(document, dict)
        self.assertIn("jobs", document)

    def test_duplicate_key_guard_actually_detects_duplicates(self) -> None:
        """Negative control: the guard must reject a workflow that reintroduces
        a duplicate `g5-recovery` job."""
        broken = "jobs:\n  g5-recovery:\n    runs-on: ubuntu-latest\n  g5-recovery:\n    runs-on: ubuntu-latest\n"
        with self.assertRaises(yaml.constructor.ConstructorError):
            yaml.load(broken, Loader=_DuplicateKeyGuard)

    def test_workflow_declares_exactly_the_expected_jobs(self) -> None:
        document = yaml.load(self.text, Loader=_DuplicateKeyGuard)
        self.assertEqual(EXPECTED_JOBS, set(document["jobs"].keys()))

    def test_top_level_job_keys_are_unique_in_raw_text(self) -> None:
        """Text-level guard, independent of any YAML loader behaviour."""
        names: list[str] = []
        in_jobs = False
        for line in self.text.splitlines():
            if line.rstrip() == "jobs:":
                in_jobs = True
                continue
            if not in_jobs:
                continue
            if line.strip() and not line.startswith(" "):
                break
            if (
                line.startswith("  ")
                and not line.startswith("   ")
                and line.rstrip().endswith(":")
            ):
                names.append(line.strip()[:-1])
        self.assertEqual(sorted(names), sorted(EXPECTED_JOBS), names)
        self.assertEqual(len(names), len(set(names)), f"duplicate jobs: {names}")

    def test_recovery_command_shape_is_present(self) -> None:
        self.assertIn("APPROVE G5 RECOVERY", self.text)
        self.assertIn("gwc:g4-authority-receipt", self.text)

    def test_gate_contract_declares_lane_integrity_obligations(self) -> None:
        text = CONTRACT.read_text(encoding="utf-8")
        for marker in LANE_MARKERS:
            self.assertIn(marker, text, f"missing in gate contract: {marker}")

    def test_instruction_surfaces_declare_lane_integrity_obligations(self) -> None:
        for surface in INSTRUCTION_SURFACES:
            # Surfaces are pre-composed effective-instruction strings
            # (composer + gwc-governed-base.md for ChatGPT) per SCRUM-404 / #441.
            text = surface if isinstance(surface, str) else surface.read_text(encoding="utf-8")
            label = "chatgpt-composed" if isinstance(surface, str) else surface.name
            for marker in LANE_MARKERS:
                self.assertIn(marker, text, f"missing in {label}: {marker}")


if __name__ == "__main__":
    unittest.main()
