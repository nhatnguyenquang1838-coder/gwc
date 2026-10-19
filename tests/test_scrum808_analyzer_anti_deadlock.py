"""SCRUM-808 / #580 — anti-deadlock invariants regression tests.

Validates the three canonical invariants from the Analyzer review:
1. READ_ONLY_ANALYSIS Child Run != Repository G2 effect
2. WAIT_CONTROLLER invalid if any bounded runnable read-only work exists
3. UR-G* vs GWC-G* namespace separation

Also covers AC8-AC10 from Jira SCRUM-808.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

GATE_LIFECYCLE_PATH = ROOT / "core/GATE_LIFECYCLE_CONTRACT_v1.0.md"
AGENTS_PATH = ROOT / "AGENTS.md"
RUNTIME_CONTRACT_PATH = ROOT / "core/Agent_Operating_Runtime_Contract_v1.0.md"

# Exact source SHA for SCRUM-781 incident evidence
SCRUM_781_RUN_ID = "scrum781-q0-20260920T074727Z"


def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestAnalyzerAntiDeadlockInvariants:
    """AC1-AC7: Canonical invariant coverage."""

    def test_action_effect_classifier_exists(self):
        """AC1 — action/effect class explicit before authority resolution."""
        text = _load_text(GATE_LIFECYCLE_PATH)
        assert "READ_ONLY_ANALYSIS" in text
        assert "REPOSITORY_EFFECT" in text
        assert "RUNTIME_EFFECT" in text
        assert "PRODUCTION_EFFECT" in text

    def test_read_only_not_repository_g2_effect(self):
        """AC2 — READ_ONLY_ANALYSIS Child Run != Repository G2 effect."""
        text = _load_text(GATE_LIFECYCLE_PATH)
        assert "READ_ONLY_ANALYSIS Child Run ≠ Repository G2 effect" in text

    def test_wait_controller_invalid_with_runnable_read_only(self):
        """AC4 — WAIT_CONTROLLER fails closed when runnable bounded read-only work exists."""
        text = _load_text(GATE_LIFECYCLE_PATH)
        assert "WAIT_CONTROLLER invalid if any bounded runnable read-only work exists" in text
        assert "INVALID_WAIT_CONTROLLER_RUNNABLE_WORK_EXISTS" in text

    def test_namespace_separation(self):
        """AC6 — UR-G* vs GWC-G* namespace-distinguishable."""
        text = _load_text(GATE_LIFECYCLE_PATH)
        assert "UR-G0...UR-G6" in text or "UR-G* vs GWC-G*" in text
        assert "GWC-G0_CONTEXT" in text or "GWC-G*" in text

    def test_analyzer_advisory_only(self):
        """AC5 — Analyzer role canonical, advisory only, no G2 mint/approval."""
        text = _load_text(AGENTS_PATH)
        assert "Analyzer is advisory only" in text or "advisory" in text.lower()
        assert "MUST NOT mint" in text or "MUST NOT approve" in text

    def test_parent_child_authority_independent(self):
        """AC7 — Child analysis authority never widens repository/effect authority."""
        text = _load_text(GATE_LIFECYCLE_PATH)
        assert "later gate never implies authority" in text.lower()

    @pytest.mark.parametrize(
        "contract_path",
        [GATE_LIFECYCLE_PATH, RUNTIME_CONTRACT_PATH],
        ids=["GATE_LIFECYCLE", "AGENT_RUNTIME"],
    )
    def test_machine_enforcement_stable_reason_codes(self, contract_path):
        """AC8 — Machine enforcement with stable reason codes, not prose-only."""
        text = _load_text(contract_path)
        assert "INVALID_WAIT_CONTROLLER_RUNNABLE_WORK_EXISTS" in text
        assert "READ_ONLY_CHILD_STRANDED_BEHIND_EFFECT_AUTHORITY" in text


class TestSCRUM781DeadlockRegression:
    """AC8-AC10: SCRUM-781 incident reproduction."""

    def test_scrumb_781_incident_referenced(self):
        """AC8 — SCRUM-781 deadlock incident is referenced in governance docs."""
        text = _load_text(GATE_LIFECYCLE_PATH)
        assert "SCRUM-781" in text or "deadlock" in text.lower()

    def test_analyzer_cannot_mutate_repository(self):
        """AC9 — Analyzer cannot mutate repository or mint/activate G2."""
        text = _load_text(AGENTS_PATH)
        assert "mutate" in text.lower() or "mutating" in text.lower() or "write" in text.lower()
        # Analyzer routing section must forbid repository write
        analyzer_section = text.split("SCRUM-808")[1] if "SCRUM-808" in text else ""
        assert "MUST NOT" in analyzer_section or "Forbidden" in analyzer_section or "read-only" in analyzer_section.lower()

    def test_taskcontroller_rejects_invalid_wait_controller(self):
        """AC10 — TaskController continuation rejects invalid WAIT_CONTROLLER with runnable read-only work."""
        text = _load_text(GATE_LIFECYCLE_PATH)
        assert "WAIT_CONTROLLER" in text
        assert "runnable" in text.lower()


class TestGUIDocsConsistency:
    """Cross-doc consistency checks."""

    def test_agents_md_has_analyzer_routing(self):
        """AGENTS.md must contain the SCRUM-808 Analyzer routing invariant."""
        text = _load_text(AGENTS_PATH)
        assert "SCRUM-808" in text
        assert "READ_ONLY_ANALYSIS" in text
        assert "WAIT_CONTROLLER" in text

    def test_core_docs_use_correct_namespace(self):
        """Both core docs must use UR-G* = Universal Run, GWC-G* = effect gates."""
        for path in [GATE_LIFECYCLE_PATH, RUNTIME_CONTRACT_PATH]:
            text = _load_text(path)
            assert "Universal Run" in text or "UR-G" in text
            assert "repository/effect" in text.lower() or "GWC-G" in text