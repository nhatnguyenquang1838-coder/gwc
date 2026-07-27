import unittest

from tools.node_architect.viewer.registry_adapter import (
    build_cytoscape_elements,
    build_scenario_decision_elements,
)
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


SCENARIO_DECISION = {
    "decision_id": "sha256:abc",
    "scenario_id": "ci-failure",
    "scenario_version": "1.0.0",
    "classification": "BLOCKED",
    "graph_revision": "sha256:g",
    "facts_digest": "sha256:f",
    "candidate_routes": [
        {
            "rank": 1,
            "class": "BLOCKED",
            "path": [
                "repo_delivery.ci-run-capture",
                "failure_recovery.timeout-recovery",
            ],
        }
    ],
    "selected_route": None,
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
        self.assertTrue(any(node["data"].get("kind") == "run" for node in elements["nodes"]))
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

    def test_scenario_overlay_edges_are_non_executable(self):
        overlay = build_scenario_decision_elements(SCENARIO_DECISION)
        self.assertTrue(any(node["data"].get("kind") == "scenario" for node in overlay["nodes"]))
        self.assertTrue(any(node["data"].get("kind") == "candidate-route" for node in overlay["nodes"]))
        self.assertTrue(all(not edge["data"]["runtime_executable"] for edge in overlay["edges"]))
        self.assertTrue(all("visual-only" in edge["classes"] for edge in overlay["edges"]))

    def test_registry_adapter_accepts_scenario_decision(self):
        bundle = {
            "nodes": {
                "nodes": [
                    {
                        "id": "repo_delivery.ci-run-capture",
                        "family": "repo_delivery",
                        "maturity": "candidate",
                        "source_status": "canonical_explicit",
                        "provenance": {},
                    },
                    {
                        "id": "failure_recovery.timeout-recovery",
                        "family": "failure_recovery",
                        "maturity": "candidate",
                        "source_status": "canonical_explicit",
                        "provenance": {},
                    },
                ]
            },
            "graph": {"edges": []},
        }
        elements = build_cytoscape_elements(bundle, scenario_decision=SCENARIO_DECISION)
        self.assertTrue(any(node["data"].get("kind") == "scenario" for node in elements["nodes"]))
        projected_edges = [
            edge
            for edge in elements["edges"]
            if edge["data"]["edge_type"].startswith("scenario-")
        ]
        self.assertTrue(projected_edges)
        self.assertTrue(all(not edge["data"]["runtime_executable"] for edge in projected_edges))

    def test_missing_scenario_decision_id_is_rejected(self):
        with self.assertRaises(ValueError):
            build_scenario_decision_elements({"scenario_id": "ci-failure"})


if __name__ == "__main__":
    unittest.main()
