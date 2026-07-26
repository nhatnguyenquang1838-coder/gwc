from __future__ import annotations

from pathlib import Path
import unittest

from tools.node_architect.viewer.registry_adapter import (
    build_cytoscape_elements,
    classify_route,
    enumerate_routes_to_green,
    load_registry_bundle,
)


ROOT = Path(__file__).resolve().parents[1]


class V3RegistryAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle = load_registry_bundle(ROOT)

    def test_full_graph_is_retained_and_inactive_nodes_are_dimmed(self) -> None:
        active = {"repo_delivery.ci-run-capture", "runtime_checkpoint.checkpoint-persist"}
        elements = build_cytoscape_elements(self.bundle, active)
        self.assertEqual(len(elements["nodes"]), 81)
        classes = {element["data"]["id"]: element["classes"] for element in elements["nodes"]}
        self.assertIn("active", classes["repo_delivery.ci-run-capture"])
        self.assertIn("inactive", classes["failure_recovery.timeout-recovery"])
        self.assertTrue(all("maturity" in element["data"] for element in elements["nodes"]))
        self.assertTrue(all("provenance" in element["data"] for element in elements["nodes"]))

    def test_visual_scaffold_edges_are_present_but_not_runtime(self) -> None:
        elements = build_cytoscape_elements(self.bundle)
        visual = [edge for edge in elements["edges"] if edge["data"]["edge_type"] == "visualization"]
        self.assertTrue(visual)
        self.assertTrue(all("visual-only" in edge["classes"] for edge in visual))
        self.assertTrue(all(edge["data"]["runtime_executable"] is False for edge in visual))

    def test_all_bounded_runtime_routes_to_green_are_enumerated(self) -> None:
        routes = enumerate_routes_to_green(
            self.bundle,
            ["repo_delivery.ci-run-capture"],
            ["validation_quality.ci-evidence-capture", "failure_recovery.timeout-recovery"],
        )
        self.assertEqual(
            {tuple(route) for route in routes},
            {
                ("repo_delivery.ci-run-capture", "runtime_checkpoint.checkpoint-persist", "validation_quality.ci-evidence-capture"),
                ("repo_delivery.ci-run-capture", "failure_recovery.timeout-recovery"),
            },
        )

    def test_route_classification_preserves_human_boundary(self) -> None:
        route = ["repo_delivery.ci-run-capture", "failure_recovery.timeout-recovery"]
        self.assertEqual(
            classify_route(route, ["failure_recovery.timeout-recovery"], ["failure_recovery.timeout-recovery"]),
            "HUMAN_REQUIRED",
        )


if __name__ == "__main__":
    unittest.main()
