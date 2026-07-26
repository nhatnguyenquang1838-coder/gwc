from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "tools/node_architect/validate_runtime_registry.py"


class RuntimeRegistryValidationTests(unittest.TestCase):
    def test_canonical_registries_pass_cross_registry_validation(self) -> None:
        result = subprocess.run(
            [sys.executable, str(VALIDATOR), "--root", str(ROOT)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["outcome"], "PASS")
        self.assertEqual(report["counts"]["nodes"], 81)
        self.assertEqual(report["counts"]["proposed_nodes"], 77)
        self.assertEqual(report["counts"]["explicit_nodes"], 4)
        self.assertEqual(report["counts"]["declared_scenarios"], 116)
        self.assertEqual(report["counts"]["materialized_scenarios"], 3)

    def test_every_slot_has_maturity_and_provenance(self) -> None:
        registry = json.loads((ROOT / "core/node-architect/node-registry.json").read_text(encoding="utf-8"))
        self.assertEqual(len(registry["nodes"]), 81)
        self.assertEqual({node["family"] for node in registry["nodes"]}, {
            "intake_context", "gate_authority", "repo_delivery", "runtime_checkpoint",
            "validation_quality", "sync_projection", "package_export", "failure_recovery", "scale_control",
        })
        for node in registry["nodes"]:
            self.assertIn(node["maturity"], {"experimental", "candidate", "pilot", "stable", "deprecated", "retired"})
            self.assertIn("source_path", node["provenance"])
            self.assertIn("source_sha", node["provenance"])
            if node["source_status"] == "proposed_registry_slot":
                self.assertNotEqual(node["maturity"], "stable")

    def test_scenario_count_is_not_graph_edge_count(self) -> None:
        scenarios = json.loads((ROOT / "core/node-architect/scenario-registry.json").read_text(encoding="utf-8"))
        graph = json.loads((ROOT / "core/node-architect/runtime-graph-registry.json").read_text(encoding="utf-8"))
        self.assertEqual(scenarios["declared_scenario_count"], 116)
        self.assertEqual(scenarios["materialized_scenario_count"], 3)
        self.assertNotEqual(scenarios["declared_scenario_count"], len(graph["edges"]))

    def test_visual_edges_are_non_executable(self) -> None:
        graph = json.loads((ROOT / "core/node-architect/runtime-graph-registry.json").read_text(encoding="utf-8"))
        visual = [edge for edge in graph["edges"] if edge["edge_type"] == "visualization"]
        self.assertTrue(visual)
        self.assertTrue(all(edge["runtime_executable"] is False for edge in visual))


if __name__ == "__main__":
    unittest.main()
