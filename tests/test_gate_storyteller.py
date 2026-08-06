from __future__ import annotations

import unittest

from tools.node_architect.build_run_graph import build_run_graph
from tools.node_architect.render_gate_story import build_gate_story
from tests.test_run_graph_builder import manifest


class GateStoryTests(unittest.TestCase):
    def test_story_contains_all_gates_and_only_actual_participants(self):
        graph = build_run_graph(manifest())
        story = build_gate_story(
            graph,
            gate_statuses={
                "G3_PR": "not_executed",
                "G4_MERGE": "not_executed",
                "G5_DEPLOY": "not_executed",
                "G6_PRODUCTION_DATA": "not_applicable",
            },
        )
        self.assertEqual(7, len(story["gates"]))
        by_gate = {item["gate"]: item for item in story["gates"]}
        self.assertEqual(["intake_context.context-snapshot"], by_gate["G0_CONTEXT"]["participating_nodes"])
        self.assertEqual(["g1-alignment-decision"], by_gate["G1_ALIGNMENT"]["participating_nodes"])
        self.assertEqual("not_executed", by_gate["G4_MERGE"]["status"])
        self.assertEqual([], by_gate["G4_MERGE"]["participating_nodes"])
        self.assertIn("không có runtime event", by_gate["G4_MERGE"]["narrative"])
        self.assertEqual("not_applicable", by_gate["G6_PRODUCTION_DATA"]["status"])
        self.assertTrue(story["story_digest"].startswith("sha256:"))

    def test_story_is_derived_from_node_actions_and_evidence(self):
        graph = build_run_graph(manifest())
        story = build_gate_story(graph)
        g2 = next(item for item in story["gates"] if item["gate"] == "G2_EXECUTION")
        self.assertIn("resolve_execution_node", g2["narrative"])
        self.assertIn("route:g2-resolve-execution-node", g2["evidence_refs"])
        self.assertIn("merge", g2["authority_not_granted"])


if __name__ == "__main__":
    unittest.main()
