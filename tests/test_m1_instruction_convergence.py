"""SCRUM-781 M1 regressions for New Runtime instruction convergence."""
import unittest
from pathlib import Path

from tools.node_architect.gate_node_routes import select_route_pack

ROOT = Path(__file__).resolve().parents[1]


PROSE_LURES = [
    "autonomous",
    "continue",
    "Human only merges main",
    "legacy compatibility",
    "historical envelope",
    "Slack MVP",
]


class M1InstructionConvergenceTests(unittest.TestCase):
    def test_route_pack_selector_ignores_prose_and_accepts_only_exact_structured_scenario(self):
        for lure in PROSE_LURES:
            self.assertIsNone(select_route_pack(lure))
        self.assertEqual(select_route_pack("ci_failure"), "RP-03")

    def test_fresh_instruction_package_declares_universal_default_and_compatibility_boundary(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        project = (ROOT / "projects/gwc/project-instructions.md").read_text(encoding="utf-8")
        extension = (ROOT / "projects/gwc/project-extension.md").read_text(encoding="utf-8")
        hermes = (ROOT / "agents/hermes/agent-instructions.md").read_text(encoding="utf-8")
        autonomous = (ROOT / "agents/autonomous-agent/agent-instructions.md").read_text(encoding="utf-8")
        executor = (ROOT / "skills/executor/SKILL.md").read_text(encoding="utf-8")

        for text in (agents, project, extension, hermes, autonomous, executor):
            self.assertIn("UNIVERSAL_RUN_NEW_RUNTIME", text)
            self.assertIn("compatibility", text.lower())
            self.assertIn("explicit", text.lower())

        self.assertIn("Hermes Universal Runtime Execution Provider", hermes)
        self.assertNotIn("Slack MVP", hermes.splitlines()[0])
        self.assertNotIn("CONTINUE | WAIT_CONTROLLER | TERMINAL", hermes)
        self.assertNotIn("At `WAIT_CONTROLLER`, stop", hermes)
        self.assertIn("Slack is an optional compatibility adapter", autonomous)
        self.assertIn("load the shared Slack protocol only when", autonomous)
        self.assertNotIn("plus the shared Slack protocol", autonomous)
        self.assertIn("reporting occurs through the bound execution provider", hermes)
        self.assertIn("If the current route explicitly binds the Slack compatibility adapter", hermes)
        self.assertIn("Slack protocol is an explicit compatibility overlay", executor)

    def test_historical_markers_do_not_enable_shadow_compatibility_replay(self):
        from tests.test_scrum_566_w8_canonical_shadow_route import (
            _activation,
            _event,
            _graph,
            _observed,
            _profile,
            _registry,
            _semantic_source,
        )
        from tools.node_architect.shadow_orchestrator import run_shadow_event

        replay_event = _event(input_payload={
            "route": "autonomous",
            "history": "old pre-prod evidence / Slack MVP / old loop",
        })
        out = run_shadow_event(
            replay_event,
            _registry(),
            _activation(),
            observed_revision="b" * 40,
            observed_state=_observed(),
            profile=_profile(),
            graph_registry=_graph(),
            root=ROOT,
            source_resolver=_semantic_source,
            policy_registry={"canonical_minimums": {"G2_EXECUTION": {"min_decision": "REQUIRED"}}},
            compatibility_replay=False,
        )
        self.assertEqual(out["status"], "SHADOW_EXECUTED")
        self.assertEqual(out["reason_code"], "SHADOW_ROUTE_EXECUTED")
        self.assertEqual(out["route_pack"], "RP-03")
        self.assertEqual(out["selected_node_count"], 1)
        self.assertEqual(out["authoritative_effect"], "NONE")
        self.assertFalse(out["authority_granted"])


if __name__ == "__main__":
    unittest.main()
