import unittest

from tools.p3_backward_graph import CompileError, compile_backward_graph, enumerate_routes, evaluate_guard


class BackwardCompilerTests(unittest.TestCase):
    def test_deterministic_dependency_closure(self):
        nodes = [
            {"id": "green", "dependencies": ["b", "a"]},
            {"id": "a", "dependencies": ["read"]},
            {"id": "b", "dependencies": []},
            {"id": "read", "dependencies": []},
            {"id": "safe", "dependencies": []},
        ]
        result = compile_backward_graph(nodes, "green", "safe")
        self.assertEqual(result["selected_nodes"], ["read", "a", "b", "green"])
        self.assertTrue(result["graph_revision"].startswith("sha256:"))

    def test_cycle_is_rejected(self):
        nodes = [
            {"id": "green", "dependencies": ["a"]},
            {"id": "a", "dependencies": ["green"]},
            {"id": "safe", "dependencies": []},
        ]
        with self.assertRaisesRegex(CompileError, "CYCLE_UNSAFE"):
            compile_backward_graph(nodes, "green", "safe")

    def test_authority_boundary_is_not_auto_promoted(self):
        nodes = [
            {"id": "green", "dependencies": ["merge"]},
            {"id": "merge", "authority": "G4_MERGE", "dependencies": []},
            {"id": "safe", "dependencies": []},
        ]
        with self.assertRaisesRegex(CompileError, "AUTHORITY_MISMATCH"):
            compile_backward_graph(nodes, "green", "safe")


class GuardAndRouteTests(unittest.TestCase):
    def test_guard_equality_is_type_strict(self):
        result = evaluate_guard({"type": "equals", "field": "value", "value": 1}, {"value": True})
        self.assertFalse(result.passed)

    def test_all_paths_are_classified_and_ranked(self):
        nodes = [
            {"id": "start", "successors": ["human", "auto", "conditional"]},
            {"id": "auto", "successors": ["green"]},
            {"id": "human", "authority": "G4_MERGE", "successors": ["green"]},
            {
                "id": "conditional",
                "guards": [{"type": "exists", "field": "ci", "conditional": True}],
                "successors": ["green"],
            },
            {"id": "green", "successors": []},
        ]
        routes = enumerate_routes(nodes, "start", "green", {})
        self.assertEqual([route["class"] for route in routes], ["VALID_AUTO", "VALID_HUMAN", "CONDITIONAL"])
        self.assertEqual([route["rank"] for route in routes], [1, 2, 3])

    def test_unsafe_route_ranks_last(self):
        nodes = [
            {"id": "start", "successors": ["unsafe", "auto"]},
            {"id": "auto", "successors": ["green"]},
            {"id": "unsafe", "unsafe": True, "successors": ["green"]},
            {"id": "green", "successors": []},
        ]
        routes = enumerate_routes(nodes, "start", "green", {})
        self.assertEqual(routes[-1]["class"], "UNSAFE")


if __name__ == "__main__":
    unittest.main()
