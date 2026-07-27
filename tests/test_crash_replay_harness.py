from pathlib import Path
import unittest

from tools.node_architect.crash_replay_harness import (
    CrashBoundary,
    CrashReplayHarness,
    parse_scenario_matrix,
    verify_matrix,
)

ROOT = Path(__file__).resolve().parents[1]


class CrashReplayHarnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenarios = parse_scenario_matrix(
            ROOT / ".gwc/tasks/SCRUM-106/g1/decision/P2_SCENARIO_MATRIX.md"
        )
        cls.harness = CrashReplayHarness(
            task_id="SCRUM-110",
            repository="nhatnguyenquang1838-coder/gwc",
            base_sha="53b23f38cf7412fffd8bc1adce8c3d6b8277b1b6",
            scope_hash="sha256:" + "a" * 64,
            graph_revision="scrum-106-p2-scenario-matrix-r2",
        )

    def test_matrix_has_27_scenarios_and_all_boundaries(self):
        self.assertEqual(len(self.scenarios), 27)
        self.assertEqual({scenario.boundary for scenario in self.scenarios}, set(CrashBoundary))

    def test_every_scenario_rejects_stale_worker_and_duplicate_effect(self):
        results = verify_matrix(self.scenarios, self.harness)
        self.assertTrue(all(result.stale_worker_rejected for result in results))
        self.assertTrue(all(result.duplicate_effect_prevented for result in results))

    def test_b3_bounded_write_reconciles_one_effect(self):
        scenario = next(
            item
            for item in self.scenarios
            if item.scenario_id == "P2-BW-TIMEOUT_AFTER_EFFECT"
        )
        result = self.harness.run(scenario)
        self.assertEqual(result.external_effect_count, 1)
        self.assertFalse(result.human_required)

    def test_b4_ambiguous_state_requires_human(self):
        scenario = next(
            item
            for item in self.scenarios
            if item.scenario_id == "P2-BW-AMBIGUOUS_POST_STATE"
        )
        result = self.harness.run(scenario)
        self.assertTrue(result.human_required)
        self.assertIn("human.takeover.required", result.events)


if __name__ == "__main__":
    unittest.main()
