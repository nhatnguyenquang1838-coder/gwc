import unittest

from tools.p3_backward_graph import (
    BudgetExceeded,
    CompileError,
    RouteBudget,
    append_scenario_decision,
    compile_backward_graph,
    decide_scenario,
    enumerate_routes,
    evaluate_guard,
)


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

    def test_guard_can_compare_two_context_fields(self):
        result = evaluate_guard(
            {"type": "equals", "field": "head_sha", "value_from_field": "expected_head_sha"},
            {"head_sha": "abc", "expected_head_sha": "abc"},
        )
        self.assertTrue(result.passed)

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

    def test_route_budget_fails_closed_with_typed_evidence(self):
        nodes = [
            {"id": "start", "successors": ["left", "right"]},
            {"id": "left", "successors": ["green"]},
            {"id": "right", "successors": ["green"]},
            {"id": "green", "successors": []},
        ]
        with self.assertRaises(BudgetExceeded) as raised:
            enumerate_routes(nodes, "start", "green", {}, budget=RouteBudget(max_routes=1))
        self.assertEqual(raised.exception.as_dict()["code"], "BUDGET_EXCEEDED")
        self.assertTrue(raised.exception.as_dict()["fail_closed"])

    def test_dense_route_budget_is_bounded(self):
        nodes = [
            {"id": "start", "successors": ["a", "b", "c"]},
            {"id": "a", "successors": ["green"]},
            {"id": "b", "successors": ["green"]},
            {"id": "c", "successors": ["green"]},
            {"id": "green", "successors": []},
        ]
        with self.assertRaisesRegex(BudgetExceeded, "BUDGET_EXCEEDED:max_routes"):
            enumerate_routes(nodes, "start", "green", {}, budget=RouteBudget(max_routes=2))


class ScenarioDecisionTests(unittest.TestCase):
    def _scenario(self):
        return {
            "id": "ci-failure",
            "version": "1.0.0",
            "activation_facts": ["ci_status"],
            "guards": [
                {
                    "id": "ci-success",
                    "type": "equals",
                    "field": "ci_status",
                    "value": "success",
                    "conditional": False,
                    "reason": "CI_FAILED",
                }
            ],
            "route_nodes": ["start", "green"],
            "edges": [
                {
                    "source": "start",
                    "target": "green",
                    "edge_type": "runtime",
                    "runtime_executable": True,
                }
            ],
            "route_policy": {
                "start_node": "start",
                "green_targets": ["green"],
                "allowed_authorities": [],
                "max_depth": 8,
            },
        }

    def test_decision_digest_is_deterministic_and_history_is_immutable(self):
        scenario = self._scenario()
        first = decide_scenario(scenario, {"ci_status": "failure"})
        second = decide_scenario(scenario, {"ci_status": "failure"})
        self.assertEqual(first["decision_id"], second["decision_id"])
        self.assertEqual(first["classification"], "BLOCKED")
        history = []
        append_scenario_decision(history, first)
        append_scenario_decision(history, second)
        self.assertEqual(len(history), 1)
        mutated = dict(first)
        mutated["classification"] = "VALID_AUTO"
        with self.assertRaisesRegex(CompileError, "IMMUTABILITY_VIOLATION"):
            append_scenario_decision(history, mutated)

    def test_missing_activation_fact_is_conditional(self):
        decision = decide_scenario(self._scenario(), {})
        self.assertEqual(decision["classification"], "CONDITIONAL")
        self.assertFalse(decision["auto_execute"])
        self.assertIsNone(decision["selected_route"])

    def test_human_required_node_is_never_auto_promoted(self):
        scenario = self._scenario()
        scenario["guards"] = []
        decision = decide_scenario(
            scenario,
            {"ci_status": "success"},
            node_metadata=[
                {"id": "start", "authority_class": "automatic"},
                {"id": "green", "authority_class": "human_required"},
            ],
        )
        self.assertEqual(decision["classification"], "VALID_HUMAN")
        self.assertFalse(decision["auto_execute"])
        self.assertIsNotNone(decision["selected_route"])

    def test_prohibited_node_is_unsafe(self):
        scenario = self._scenario()
        scenario["guards"] = []
        decision = decide_scenario(
            scenario,
            {"ci_status": "success"},
            node_metadata=[
                {"id": "start", "authority_class": "automatic"},
                {"id": "green", "authority_class": "prohibited"},
            ],
        )
        self.assertEqual(decision["classification"], "UNSAFE")
        self.assertFalse(decision["auto_execute"])
        self.assertIsNone(decision["selected_route"])

    def test_budget_exhaustion_returns_blocked_typed_decision(self):
        scenario = self._scenario()
        decision = decide_scenario(
            scenario,
            {"ci_status": "success"},
            budget=RouteBudget(max_nodes=1),
        )
        self.assertEqual(decision["classification"], "BLOCKED")
        self.assertFalse(decision["auto_execute"])
        self.assertEqual(decision["budget_evidence"]["code"], "BUDGET_EXCEEDED")

    def test_tied_routes_are_stable_under_input_reordering(self):
        scenario = self._scenario()
        scenario["edges"] = [
            {"source": "start", "target": "green", "edge_type": "runtime", "runtime_executable": True},
        ]
        first = decide_scenario(scenario, {"ci_status": "success"})
        reordered = dict(scenario)
        reordered["route_nodes"] = list(reversed(scenario["route_nodes"]))
        second = decide_scenario(reordered, {"ci_status": "success"})
        self.assertEqual(first["decision_id"], second["decision_id"])


if __name__ == "__main__":
    unittest.main()
