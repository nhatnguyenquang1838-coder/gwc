"""Synthetic ENGINE_MECHANICS only: no host admission or DWO certification."""

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from tools.node_architect.hermes_workflow_compiler import compile_workflow, digest

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = Path(
    os.environ.get("GWC_TEST_SCRATCH", str(Path.home() / ".hermes/cache/scratch"))
)
SCRATCH.mkdir(parents=True, exist_ok=True)


def synthetic_graph(active=True):
    workflow = json.loads(
        (ROOT / "core/node-architect/hermes-loop-a2a-base-workflow-r1.json").read_text()
    )
    plan = json.loads(
        (
            ROOT / "core/node-architect/scrum781-q0-fresh-execution-plan-r2.json"
        ).read_text()
    )
    plan["goal"] = "SYNTHETIC ENGINE MECHANICS ONLY; NOT ORIGINAL DWO INCIDENT"
    plan["recursive_plan"] = {
        "id": "synthetic",
        "atomic": False,
        "children": [
            {
                "id": "synthetic-A",
                "atomic": True,
                "depends_on": [],
                "action": "synthetic sandbox validation",
            },
            {
                "id": "synthetic-B",
                "atomic": True,
                "depends_on": ["synthetic-A"],
                "action": "synthetic sandbox validation",
            },
        ],
    }
    return compile_workflow(workflow, plan, expected_plan_digest=digest(plan))


class SyntheticHost:
    """Deterministic test adapter with explicit source/readback evidence."""

    evidence_mode = "SYNTHETIC"

    def __init__(self, graph):
        self.graph = graph
        self.observations = 0
        self.effects = {}
        self.executed = []
        self.deliveries = {}
        self.wakes = []
        self.command = None
        self.cursor = 0
        self.recovery = {"performed": True, "legal_next": True}

    def observe(self, binding, high_water):
        self.observations += 1
        return {
            "controller_cursor": self.cursor,
            "executor_cursor": 0,
            "exact_readback": True,
            "source_sha": binding["source_sha"],
            "command": self.command,
        }

    def authorize(self, binding, task):
        return {
            **binding,
            "task_id": task.task_id,
            "action": "run_sandboxed_validation",
            "target": "tests/synthetic.py",
            "valid": True,
            "exact_readback": True,
            "receipt_ref": "synthetic:authority",
            "allowed_actions": ["run_sandboxed_validation"],
        }

    def execute(self, task, key):
        self.executed.append(task.task_id)
        result = {
            "key": key,
            "task_id": task.task_id,
            "accepted": True,
            "exact_readback": True,
            "receipt_ref": "synthetic:effect:" + task.task_id,
        }
        self.effects[key] = result
        return result

    def read_effect(self, key):
        return self.effects.get(key)

    def recover(self, task):
        return self.recovery

    def handoff(self, kind, payload, key):
        self.wakes.append(kind)
        self.deliveries[key] = {
            "key": key,
            "kind": kind,
            "exact_readback": True,
            "receipt_ref": "synthetic:delivery",
            "delivered": True,
        }
        return self.deliveries[key]

    def read_delivery(self, key):
        return self.deliveries.get(key)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=SCRATCH, prefix="command7-test-")
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "checkpoint.sqlite"
        self.graph = synthetic_graph()
        self.host = SyntheticHost(self.graph)
        self.binding = {
            "run_id": self.graph.run_id,
            "plan_digest": self.graph.plan_digest,
            "graph_digest": self.graph.graph_digest,
            "thread_id": "synthetic-thread",
            "host_session_id": "synthetic-session",
            "writer_id": "synthetic-writer",
            "scope_digest": digest(["tests/**"]),
            "writable_targets": ["tests/**"],
            "source_sha": "d8cedd299907933f7e67b557674ac4c0dd49425a",
            "recipient": self.graph.plan["recipient"],
            "qualified": True,
            "run_hold": False,
        }

    def runtime(self, **kwargs):
        try:
            module = importlib.import_module(
                "tools.node_architect.hermes_workflow_runtime"
            )
        except ModuleNotFoundError:
            self.fail("Missing qualified bounded workflow runtime")
        return module.WorkflowRuntime(
            self.graph, self.db, self.host, self.binding, **kwargs
        )

    def test_B2_qualified_no_mission_reads_exact_ce_and_zero_wake(self):
        runtime = self.runtime()
        state = runtime.tick(self.binding, active_mission=False, max_steps=1)
        self.assertEqual(self.host.observations, 1)
        self.assertEqual(state["observed"], {"controller": 0, "executor": 0})
        self.assertEqual(state["consumed_controller"], -1)
        self.assertEqual(self.host.executed, [])
        self.assertEqual(self.host.wakes, [])
        self.assertFalse(state["workflow_terminal"])
        self.assertFalse(state["authority_granted"])
        self.assertEqual(
            state["trace"],
            [
                "qualify_tick",
                "observe_ce",
                "reconcile_state",
                "select_frontier",
                "silent_noop",
                "end",
            ],
        )

    def controller_command(self, kind="NEXT", seq=1, **extra):
        command = {
            k: self.binding[k]
            for k in ("run_id", "plan_digest", "thread_id", "scope_digest", "recipient")
        }
        command.update(
            actor="CONTROLLER",
            seq=seq,
            kind=kind,
            exact_readback=True,
            authority_ref="synthetic:authority",
            continuation={
                "run_id": self.graph.run_id,
                "thread_id": self.binding["thread_id"],
                "plan_digest": self.graph.plan_digest,
                "controller_seq": seq,
                "exact_readback": True,
                "receipt_ref": "synthetic:continuation",
            },
        )
        command.update(extra)
        command["event_digest"] = digest(command)
        self.host.cursor = seq
        self.host.command = command

    def test_B3_B4_B8_two_dependencies_bounded_ticks_terminal_once(self):
        self.controller_command()
        runtime = self.runtime()
        state = runtime.tick(self.binding, max_steps=1)
        self.assertEqual(state["consumed_controller"], 1)
        self.assertEqual(list(state["completed"]), ["synthetic-A"])
        self.assertEqual(self.host.wakes, [])
        self.assertFalse(state["workflow_terminal"])
        state = runtime.tick(self.binding, active_mission=True, max_steps=1)
        self.assertEqual(self.host.executed, ["synthetic-A", "synthetic-B"])
        self.assertTrue(state["workflow_terminal"])
        self.assertFalse(state["authority_granted"])
        self.assertEqual(self.host.wakes, ["TASK_TERMINAL"])
        self.assertIn("execute_task", state["trace"])
        self.runtime().tick(self.binding, active_mission=True, max_steps=2)
        self.assertEqual(self.host.executed, ["synthetic-A", "synthetic-B"])
        self.assertEqual(self.host.wakes, ["TASK_TERMINAL"])

    def test_B9_invalid_command_does_not_consume_or_execute(self):
        for field, value in [
            ("actor", "EXECUTOR"),
            ("recipient", "other"),
            ("scope_digest", "wrong"),
            ("plan_digest", "wrong"),
            ("event_digest", "wrong"),
            ("continuation", {}),
        ]:
            with self.subTest(field=field):
                self.controller_command(**{field: value})
                if field == "event_digest":
                    self.host.command["event_digest"] = value
                with self.assertRaises(ValueError):
                    self.runtime().tick(self.binding, max_steps=1)
                self.assertEqual(self.host.executed, [])
                self.assertEqual(self.host.wakes, [])
                self.assertEqual(self.runtime()._load()["consumed_controller"], -1)

    def test_B5_crash_after_effect_reconciles_without_second_execute(self):
        original = self.host.execute

        def crash(task, key):
            original(task, key)
            raise RuntimeError("synthetic crash after effect")

        self.host.execute = crash
        with self.assertRaisesRegex(RuntimeError, "crash after effect"):
            self.runtime().tick(self.binding, active_mission=True)
        self.host.execute = original
        state = self.runtime().tick(self.binding, active_mission=True)
        self.assertIn("synthetic-A", state["completed"])
        self.assertEqual(self.host.executed, ["synthetic-A"])

    def test_B5_uncertain_effect_does_not_blindly_retry(self):
        calls = []

        def uncertain(task, key):
            calls.append(key)
            raise RuntimeError("synthetic transport timeout")

        self.host.execute = uncertain
        with self.assertRaises(RuntimeError):
            self.runtime().tick(self.binding, active_mission=True)
        with self.assertRaisesRegex(ValueError, "UNCERTAIN"):
            self.runtime().tick(self.binding, active_mission=True)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.host.wakes, [])

    def test_B5_overlapping_writer_is_rejected(self):
        second = self.runtime()
        original = self.host.execute

        def overlap(task, key):
            with self.assertRaisesRegex(ValueError, "WRITER_OVERLAP"):
                second.tick(self.binding, active_mission=True)
            return original(task, key)

        self.host.execute = overlap
        self.runtime().tick(self.binding, active_mission=True)
        self.assertEqual(self.host.executed, ["synthetic-A"])

    def test_B8_crash_after_wake_reconciles_delivery_once(self):
        original = self.host.handoff

        def crash(kind, payload, key):
            original(kind, payload, key)
            raise RuntimeError("synthetic crash after wake")

        self.host.handoff = crash
        with self.assertRaises(RuntimeError):
            self.runtime().tick(self.binding, active_mission=True, max_steps=2)
        self.host.handoff = original
        state = self.runtime().tick(self.binding, active_mission=True)
        self.assertTrue(state["workflow_terminal"])
        self.assertEqual(self.host.wakes, ["TASK_TERMINAL"])

    def test_B9_effect_authority_and_scope_precede_execute(self):
        original = self.host.authorize
        for patch in [
            {"action": "deploy_approved_release"},
            {"target": "../tests/x.py"},
            {"target": "core/node-architect/x.json"},
            {"valid": False},
            {"writer_id": "other"},
        ]:
            with self.subTest(patch=patch):
                self.host.authorize = lambda binding, task, patch=patch: {
                    **original(binding, task),
                    **patch,
                }
                with self.assertRaises(ValueError):
                    self.runtime().tick(self.binding, active_mission=True)
                self.assertEqual(self.host.executed, [])

    def failing_worker(self):
        original = self.host.execute

        def fail(task, key):
            receipt = original(task, key)
            receipt.update(
                accepted=False,
                failure_class="recoverable",
                failure_signature="SYNTHETIC_FAULT",
            )
            return receipt

        self.host.execute = fail
        return original

    def test_recoverable_failure_yields_locally_without_gpt_wake(self):
        original = self.failing_worker()
        self.host.recovery = {
            "performed": True,
            "exact_readback": True,
            "receipt_ref": "synthetic:recovery",
            "legal_next": True,
            "retry_safe": True,
        }
        state = self.runtime().tick(self.binding, active_mission=True)
        self.assertEqual(state["completed"], {})
        self.assertEqual(self.host.wakes, [])
        self.host.execute = original
        state = self.runtime().tick(self.binding, active_mission=True)
        self.assertIn("synthetic-A", state["completed"])
        self.assertEqual(len(self.host.executed), 2)

    def test_B6_B7_deadlock_once_exact_unlock_same_thread_task(self):
        original = self.failing_worker()
        self.host.recovery = {
            "performed": True,
            "exact_readback": True,
            "receipt_ref": "synthetic:recovery",
            "legal_next": False,
            "retry_safe": True,
            "owner": "CONTROLLER",
            "release_trigger": "typed UNLOCK",
            "alternatives": ["provide input", "revise scope"],
        }
        state = self.runtime().tick(self.binding, active_mission=True)
        self.assertFalse(state["workflow_terminal"])
        self.assertEqual(self.host.wakes, ["VERIFIED_DEADLOCK_UNLOCK"])
        self.assertEqual(state["blocked"]["task_id"], "synthetic-A")
        key = state["blocked"]["key"]
        self.runtime().tick(self.binding, active_mission=True)
        self.assertEqual(len(self.host.executed), 1)
        self.assertEqual(self.host.wakes, ["VERIFIED_DEADLOCK_UNLOCK"])
        self.controller_command(
            kind="UNLOCK", seq=2, blocker_key="wrong", task_id="synthetic-A"
        )
        with self.assertRaisesRegex(ValueError, "UNLOCK_BINDING"):
            self.runtime().tick(self.binding)
        self.controller_command(
            kind="UNLOCK", seq=2, blocker_key=key, task_id="synthetic-A"
        )
        self.host.execute = original
        state = self.runtime().tick(self.binding)
        self.assertIn("synthetic-A", state["completed"])
        self.assertIsNone(state["blocked"])
        self.assertEqual(state["consumed_controller"], 2)
        state = self.runtime().tick(self.binding)
        self.assertTrue(state["workflow_terminal"])
        self.assertEqual(self.host.wakes, ["VERIFIED_DEADLOCK_UNLOCK", "TASK_TERMINAL"])
        self.assertEqual(self.binding["thread_id"], "synthetic-thread")

    def test_budget_or_unverified_recovery_is_not_deadlock(self):
        self.failing_worker()
        self.host.recovery = {
            "performed": False,
            "legal_next": False,
            "owner": "CONTROLLER",
        }
        state = self.runtime().tick(self.binding, active_mission=True)
        self.assertEqual(self.host.wakes, [])
        self.assertFalse(state["workflow_terminal"])

    def test_optional_langgraph_real_stategraph_same_receipts_restart(self):
        try:
            importlib.import_module("langgraph.graph")
        except ImportError:
            self.skipTest(
                "Optional LangGraph dependency not installed in this interpreter"
            )
        runtime = self.runtime(backend="langgraph")
        self.controller_command()
        state = runtime.tick(self.binding, max_steps=1)
        self.assertEqual(list(state["completed"]), ["synthetic-A"])
        self.assertEqual(
            state["trace"][:3], ["qualify_tick", "observe_ce", "reconcile_state"]
        )
        self.assertEqual(self.host.wakes, [])
        state = self.runtime(backend="langgraph").tick(self.binding)
        self.assertTrue(state["workflow_terminal"])
        self.assertEqual(self.host.executed, ["synthetic-A", "synthetic-B"])
        self.assertEqual(self.host.wakes, ["TASK_TERMINAL"])
        self.assertEqual(
            set(runtime.executable_graph.get_graph().nodes) - {"__start__", "__end__"},
            {n["id"] for n in self.graph.nodes},
        )

    def test_every_runtime_edge_matches_compiled_definition(self):
        from tools.node_architect.hermes_workflow_compiler import EDGES

        self.controller_command()
        state = self.runtime().tick(self.binding, max_steps=2)
        for source, target in zip(state["trace"], state["trace"][1:]):
            self.assertIn(target, EDGES[source], (source, target))

    def test_checkpoint_completed_requires_canonical_effect_readback(self):
        self.runtime().tick(self.binding, active_mission=True)
        self.host.effects.clear()
        with self.assertRaisesRegex(ValueError, "CHECKPOINT_EFFECT"):
            self.runtime().tick(self.binding, active_mission=True)
        self.assertEqual(self.host.executed, ["synthetic-A"])
        self.assertEqual(self.host.wakes, [])

    def test_pending_wake_without_readback_is_not_sent_again(self):
        calls = []

        def timeout(kind, payload, key):
            calls.append(key)
            raise RuntimeError("synthetic send ambiguity")

        self.host.handoff = timeout
        with self.assertRaises(RuntimeError):
            self.runtime().tick(self.binding, active_mission=True, max_steps=2)
        with self.assertRaisesRegex(ValueError, "UNCERTAIN"):
            self.runtime().tick(self.binding, active_mission=True)
        self.assertEqual(len(calls), 1)
        self.assertFalse(self.runtime()._load()["workflow_terminal"])

    def test_B9_source_and_cursor_readback_are_binding_not_hints(self):
        original = self.host.observe
        for change in [
            {"source_sha": "c" * 40},
            {"exact_readback": False},
            {"controller_cursor": "1"},
        ]:
            with self.subTest(change=change):
                self.host.observe = lambda binding, high_water, change=change: {
                    **original(binding, high_water),
                    **change,
                }
                with self.assertRaises(ValueError):
                    self.runtime().tick(self.binding, active_mission=True)
                self.assertEqual(self.host.executed, [])

    def test_B9_wrong_session_and_hold_fail_before_observation(self):
        runtime = self.runtime()
        for key, value in [
            ("host_session_id", "wrong"),
            ("run_id", "wrong"),
            ("plan_digest", "wrong"),
            ("writer_id", "wrong"),
            ("scope_digest", "wrong"),
            ("run_hold", True),
            ("qualified", False),
        ]:
            with self.subTest(key=key):
                changed = {**self.binding, key: value}
                with self.assertRaises(ValueError):
                    runtime.tick(changed, active_mission=True, max_steps=1)
        self.assertEqual(self.host.observations, 0)
        self.assertEqual(self.host.executed, [])


class LangGraphRuntimeTests(RuntimeTests):
    """Run the same safety mechanics through the actual optional engine."""

    def setUp(self):
        try:
            importlib.import_module("langgraph.graph")
        except ImportError:
            self.skipTest("Optional LangGraph not installed")
        super().setUp()

    def runtime(self, **kwargs):
        kwargs.setdefault("backend", "langgraph")
        return super().runtime(**kwargs)


if __name__ == "__main__":
    unittest.main()
