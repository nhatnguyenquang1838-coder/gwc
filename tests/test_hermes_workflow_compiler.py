"""Executable graph compilation, without granting host/effect authority."""

import copy
import importlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class WorkflowCompilerTests(unittest.TestCase):
    def setUp(self):
        self.workflow = json.loads(
            (
                ROOT / "core/node-architect/hermes-loop-a2a-base-workflow-r1.json"
            ).read_text()
        )
        self.plan = json.loads(
            (
                ROOT / "core/node-architect/scrum781-q0-fresh-execution-plan-r2.json"
            ).read_text()
        )

    def compiler(self):
        try:
            return importlib.import_module(
                "tools.node_architect.hermes_workflow_compiler"
            )
        except ModuleNotFoundError:
            self.fail("Missing executable RuntimePlan-bound workflow compiler")

    def test_B1_compile_exact_plan_and_deterministic_identity(self):
        compiler = self.compiler()
        digest = compiler.digest(self.plan)
        graph = compiler.compile_workflow(
            self.workflow, self.plan, expected_plan_digest=digest
        )
        self.assertEqual(len(graph.nodes), 14)
        self.assertEqual(graph.plan_digest, digest)
        self.assertEqual(
            graph.graph_digest,
            compiler.compile_workflow(
                copy.deepcopy(self.workflow),
                copy.deepcopy(self.plan),
                expected_plan_digest=digest,
            ).graph_digest,
        )
        self.assertFalse(graph.authority_granted)
        changed = copy.deepcopy(self.plan)
        changed["goal"] += " drift"
        with self.assertRaisesRegex(ValueError, "PLAN_DIGEST_MISMATCH"):
            compiler.compile_workflow(
                self.workflow, changed, expected_plan_digest=digest
            )

    def test_B1_reject_unsupported_structure_and_plan_cycles(self):
        compiler = self.compiler()
        for mutation, reason in [
            (lambda w: w["nodes"][0].update(kind="shell"), "UNSUPPORTED_NODE_TYPE"),
            (lambda w: w["nodes"][0].update(next="missing"), "DANGLING_EDGE"),
            (lambda w: w["nodes"][0].update(next="execute_task"), "UNSUPPORTED_EDGE"),
            (lambda w: w["nodes"][0].update(effect="deploy"), "UNSUPPORTED_NODE_FIELD"),
            (
                lambda w: w["nodes"][6].update(impl="shell"),
                "UNAUTHORIZED_EFFECT_ADAPTER",
            ),
            (lambda w: w["nodes"][0].update(checks=[]), "UNSUPPORTED_NODE_CONTRACT"),
        ]:
            with self.subTest(reason=reason):
                changed = copy.deepcopy(self.workflow)
                mutation(changed)
                with self.assertRaisesRegex(ValueError, reason):
                    compiler.compile_workflow(
                        changed,
                        self.plan,
                        expected_plan_digest=compiler.digest(self.plan),
                    )
        changed_plan = copy.deepcopy(self.plan)
        changed_plan["recursive_plan"]["children"][0]["children"][0]["depends_on"] = [
            "F2-PRECHECK-DAG"
        ]
        with self.assertRaisesRegex(ValueError, "PLAN_DEPENDENCY_CYCLE"):
            compiler.compile_workflow(
                self.workflow,
                changed_plan,
                expected_plan_digest=compiler.digest(changed_plan),
            )

    def test_B1_closed_workflow_metadata_and_declared_digest(self):
        compiler = self.compiler()
        for mutate, reason in [
            (lambda w: w.update(effect="deploy"), "UNSUPPORTED_WORKFLOW_FIELD"),
            (lambda w: w.update(engine="shell"), "UNSUPPORTED_WORKFLOW_ENGINE"),
            (
                lambda w: w["source_binding"].update(
                    plan_digest=compiler.digest("wrong")
                ),
                "DECLARED_PLAN_DIGEST_MISMATCH",
            ),
            (
                lambda w: w["source_binding"].update(runtimeplan_ref="other.json"),
                "UNSUPPORTED_PLAN_SOURCE",
            ),
        ]:
            with self.subTest(reason=reason):
                changed = copy.deepcopy(self.workflow)
                mutate(changed)
                with self.assertRaisesRegex(ValueError, reason):
                    compiler.compile_workflow(
                        changed,
                        self.plan,
                        expected_plan_digest=compiler.digest(self.plan),
                    )

    def test_B1_compiled_snapshot_cannot_drift(self):
        compiler = self.compiler()
        graph = compiler.compile_workflow(
            self.workflow, self.plan, expected_plan_digest=compiler.digest(self.plan)
        )
        graph.nodes[0]["next"] = "execute_task"
        self.assertEqual(graph.nodes[0]["next"], "observe_ce")
        self.assertEqual(graph.tasks[1].depends_on, ("F2-PRECHECK-SOURCE",))
        self.assertEqual(
            graph.tasks[2].depends_on, ("F2-PRECHECK-SOURCE", "F2-PRECHECK-DAG")
        )


if __name__ == "__main__":
    unittest.main()
