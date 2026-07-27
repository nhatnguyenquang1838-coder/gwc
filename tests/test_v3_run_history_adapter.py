import unittest

from tools.node_architect.viewer.registry_adapter import build_cytoscape_elements
from tools.node_architect.viewer.run_history_adapter import (
    build_run_history_elements,
    overlay_run_history,
)

HISTORY = {
    "run": {
        "run_id": "run-110",
        "task_id": "SCRUM-110",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "base_sha": "53b23f38cf7412fffd8bc1adce8c3d6b8277b1b6",
        "scope_hash": "sha256:" + "a" * 64,
        "graph_revision": "r2",
        "status": "completed",
    },
    "events": [
        {
            "event_id": "e1",
            "sequence": 1,
            "event_type": "node.started",
            "node_id": "repo_delivery.ci-run-capture",
            "gate": "G2_EXECUTION",
            "outcome": "pending",
        },
        {
            "event_id": "e2",
            "sequence": 2,
            "event_type": "node.completed",
            "node_id": "runtime_checkpoint.checkpoint-persist",
            "gate": "G2_EXECUTION",
            "outcome": "success",
        },
    ],
    "checkpoints": [
        {
            "revision": 1,
            "current_node_id": "runtime_checkpoint.checkpoint-persist",
            "next_node_id": "validation_quality.ci-evidence-capture",
            "next_action": "resume",
            "gate": "G2_EXECUTION",
            "status": "REPLAY_VERIFIED",
            "lease_owner": "worker-b",
            "fencing_token": 2,
        }
    ],
}


class V3RunHistoryAdapterTests(unittest.TestCase):
    def test_real_history_preserves_exact_ids_and_bindings(self):
        elements = build_run_history_elements(HISTORY)
        ids = {node["data"]["id"] for node in elements["nodes"]}
        self.assertIn("run:run-110", ids)
        self.assertIn("event:run-110:e1", ids)
        self.assertIn("checkpoint:run-110:1", ids)
        self.assertTrue(
            all(edge["data"]["runtime_executable"] is False for edge in elements["edges"])
        )

    def test_overlay_retains_registry_and_marks_observed_nodes(self):
        base = {
            "nodes": [
                {
                    "data": {"id": "repo_delivery.ci-run-capture"},
                    "classes": "runtime-node inactive",
                },
                {
                    "data": {"id": "runtime_checkpoint.checkpoint-persist"},
                    "classes": "runtime-node inactive",
                },
            ],
            "edges": [],
        }
        merged = overlay_run_history(base, build_run_history_elements(HISTORY))
        classes = {node["data"]["id"]: node["classes"] for node in merged["nodes"]}
        self.assertIn("history-observed", classes["repo_delivery.ci-run-capture"])
        self.assertEqual(
            len([node for node in merged["nodes"] if node["data"]["id"].startswith("run:")]),
            1,
        )

    def test_registry_adapter_accepts_real_history_without_promoting_edges(self):
        bundle = {
            "nodes": {
                "nodes": [
                    {
                        "id": "repo_delivery.ci-run-capture",
                        "family": "repo_delivery",
                        "maturity": "implemented",
                        "source_status": "implemented",
                        "provenance": "test",
                    },
                    {
                        "id": "runtime_checkpoint.checkpoint-persist",
                        "family": "runtime_checkpoint",
                        "maturity": "implemented",
                        "source_status": "implemented",
                        "provenance": "test",
                    },
                ]
            },
            "graph": {"edges": []},
        }
        elements = build_cytoscape_elements(bundle, run_history=HISTORY)
        self.assertTrue(
            any(node["data"].get("kind") == "run" for node in elements["nodes"])
        )
        history_edges = [
            edge
            for edge in elements["edges"]
            if edge["data"]["edge_type"].startswith("history")
        ]
        self.assertTrue(history_edges)
        self.assertTrue(
            all(edge["data"]["runtime_executable"] is False for edge in history_edges)
        )

    def test_missing_run_id_is_rejected(self):
        with self.assertRaises(ValueError):
            build_run_history_elements({"run": {}, "events": [], "checkpoints": []})


if __name__ == "__main__":
    unittest.main()
