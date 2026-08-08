import json
import unittest
from pathlib import Path

from tools.node_architect.validate_runtime_registry import validate_registry

ROOT = Path(__file__).resolve().parents[1]


class ExtensionTests(unittest.TestCase):
    def test_baseline_preserved_one_extension(self):
        report = validate_registry(ROOT)
        self.assertEqual(report["issues"], [], report["issues"])
        self.assertEqual(report["counts"]["nodes"], 81)
        self.assertEqual(report["counts"]["baseline_nodes"], 81)
        self.assertEqual(report["counts"]["extension_nodes"], 1)
        self.assertEqual(report["counts"]["effective_nodes"], 82)
        self.assertEqual(report["counts"]["extension_edges"], 1)

    def test_extension_is_scrum_284_node(self):
        data = json.loads(
            (ROOT / "core/node-architect/runtime-node-extension-registry.json").read_text()
        )
        self.assertEqual(data["admitted_extension_count"], 1)
        item = data["extensions"][0]
        self.assertEqual(item["extension_slot"], 82)
        self.assertEqual(item["decision_task_id"], "SCRUM-284")
        self.assertEqual(item["node"]["id"], "gate_authority.research-review-to-execution")
        self.assertEqual(
            item["node"]["provenance"]["source_path"],
            "core/node-architect/node-extensions/gate_authority/research-review-to-execution.node.json",
        )
        self.assertEqual(item["route"]["terminal_gate"], "G4_MERGE")
        self.assertEqual(item["route"]["outcome"], "HUMAN_REQUIRED")

    def test_baseline_graph_remains_exactly_81_nodes(self):
        graph = json.loads(
            (ROOT / "core/node-architect/runtime-graph-registry.json").read_text()
        )
        baseline = json.loads(
            (ROOT / "core/node-architect/node-registry.json").read_text()
        )
        baseline_ids = {node["id"] for node in baseline["nodes"]}
        self.assertEqual(len(baseline_ids), 81)
        self.assertEqual(set(graph["nodes"]), baseline_ids)
        self.assertNotIn("gate_authority.research-review-to-execution", graph["nodes"])

    def test_extension_route_binds_into_baseline_runtime(self):
        data = json.loads(
            (ROOT / "core/node-architect/runtime-node-extension-registry.json").read_text()
        )
        item = data["extensions"][0]
        self.assertEqual(
            item["route"]["nodes"][0], "gate_authority.research-review-to-execution"
        )
        self.assertEqual(
            item["route"]["edges"],
            [
                {
                    "source": "gate_authority.research-review-to-execution",
                    "target": "repo_delivery.ci-run-capture",
                    "edge_type": "runtime",
                    "runtime_executable": True,
                    "provenance": "SCRUM-284:research-execution-handoff",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
