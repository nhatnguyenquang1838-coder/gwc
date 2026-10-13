"""Pure source-bound compiler; its output grants no host/effect authority.

Only the reviewed R1 node catalogue is supported. New node/effect semantics
require a compiler revision, not an arbitrary JSON field or Python callback.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import Any


def canonical(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def digest(value: Any) -> str:
    return "sha256:" + sha256(canonical(value).encode()).hexdigest()


@dataclass(frozen=True)
class AtomicTask:
    task_id: str
    depends_on: tuple[str, ...]
    action: str


@dataclass(frozen=True)
class CompiledWorkflow:
    run_id: str
    plan_digest: str
    graph_digest: str
    workflow_json: str
    plan_json: str
    tasks: tuple[AtomicTask, ...]
    authority_granted: bool = False

    @property
    def nodes(self) -> tuple[dict, ...]:
        # Fresh projections prevent mutations behind the digest/frozen dataclass.
        return tuple(json.loads(self.workflow_json)["nodes"])

    @property
    def plan(self) -> dict:
        return json.loads(self.plan_json)


EDGES = {
    "qualify_tick": {"observe_ce"},
    "observe_ce": {"reconcile_state"},
    "reconcile_state": {"select_frontier"},
    "select_frontier": {
        "consume_command",
        "precheck",
        "terminal_handoff",
        "evaluate_blocker",
        "silent_noop",
    },
    "consume_command": {"precheck"},
    "precheck": {"execute_task", "evaluate_blocker"},
    "execute_task": {"verify_task"},
    "verify_task": {"persist_progress", "evaluate_blocker"},
    "persist_progress": {"select_frontier"},
    "evaluate_blocker": {
        "select_frontier",
        "deadlock_handoff",
        "terminal_handoff",
        "silent_noop",
    },
    "deadlock_handoff": {"silent_noop"},
    "terminal_handoff": {"end"},
    "silent_noop": {"end"},
    "end": set(),
}
NODE_CONTRACT_DIGEST = (
    "sha256:53268f285bc2b300ae4303f755f8e34a71c687c35318ee7f734351d8e65089b3"
)


def compile_tasks(root: Mapping | None) -> tuple[AtomicTask, ...]:
    records, ancestors = {}, {}

    def visit(node, parents):
        name = node.get("id")
        if not isinstance(name, str) or not name or name in records:
            raise ValueError("INVALID_PLAN_NODE")
        records[name], ancestors[name] = node, parents
        children = node.get("children", [])
        if type(node.get("atomic")) is not bool or bool(children) == node["atomic"]:
            raise ValueError("INVALID_ATOMIC_FRONTIER")
        if not isinstance(node.get("depends_on", []), list):
            raise ValueError("INVALID_PLAN_DEPENDENCIES")  # noqa: TRY004 -- closed validator API
        for child in children:
            visit(child, parents + (name,))

    if not isinstance(root, Mapping):
        raise ValueError("MISSING_RECURSIVE_PLAN")  # noqa: TRY004 -- closed validator API
    visit(root, ())
    leaves = [name for name, node in records.items() if node["atomic"]]

    def expand(name):
        if name not in records:
            raise ValueError("UNKNOWN_PLAN_DEPENDENCY")
        return [leaf for leaf in leaves if leaf == name or name in ancestors[leaf]]

    dependencies = {}
    for leaf in leaves:
        deps = set()
        for source in (*ancestors[leaf], leaf):
            for dep in records[source].get("depends_on", []):
                deps.update(expand(dep))
        dependencies[leaf] = tuple(name for name in leaves if name in deps)
    visiting, visited = set(), set()

    def cycle(name):
        if name in visiting:
            raise ValueError("PLAN_DEPENDENCY_CYCLE")
        if name in visited:
            return
        visiting.add(name)
        for dep in dependencies[name]:
            cycle(dep)
        visiting.remove(name)
        visited.add(name)

    for leaf in leaves:
        cycle(leaf)
    return tuple(
        AtomicTask(name, dependencies[name], records[name].get("action", ""))
        for name in leaves
    )


def compile_workflow(
    workflow: Mapping,
    plan: Mapping,
    *,
    expected_plan_digest: str,
    expected_graph_digest: str | None = None,
) -> CompiledWorkflow:
    actual = digest(plan)
    if set(workflow) - {
        "schema_id",
        "workflow_id",
        "intent",
        "status",
        "engine",
        "host",
        "source_binding",
        "limits",
        "state",
        "nodes",
        "invariants",
        "acceptance",
    }:
        raise ValueError("UNSUPPORTED_WORKFLOW_FIELD")
    if (
        workflow.get("schema_id") != "gwc.node-architect.workflow-base.v1"
        or workflow.get("workflow_id") != "hermes-loop-a2a-base-r1"
        or workflow.get("engine") != "langgraph"
        or workflow.get("host") != "hermes"
    ):
        raise ValueError("UNSUPPORTED_WORKFLOW_ENGINE")
    binding = workflow.get("source_binding", {})
    if binding.get("plan_digest") not in (actual, "RESOLVE_AT_MATERIALIZATION"):
        raise ValueError("DECLARED_PLAN_DIGEST_MISMATCH")
    if (
        binding.get("runtimeplan_ref")
        != "core/node-architect/scrum781-q0-fresh-execution-plan-r2.json"
    ):
        raise ValueError("UNSUPPORTED_PLAN_SOURCE")
    if actual != expected_plan_digest:
        raise ValueError("PLAN_DIGEST_MISMATCH")
    binding = workflow.get("source_binding", {})
    if not binding.get("run_id") or binding["run_id"] != plan.get("run_id"):
        raise ValueError("RUN_BINDING_MISMATCH")
    if binding.get("runtime_epoch") != plan.get("runtime_epoch"):
        raise ValueError("EPOCH_BINDING_MISMATCH")
    if binding.get("q0_gate") != plan.get("current_gate"):
        raise ValueError("GATE_BINDING_MISMATCH")
    limits, scope = workflow.get("limits", {}), plan.get("scope", {})
    if limits != {
        "max_parallel": 1,
        "child_run_creation": 0,
        "one_active_writer": True,
    }:
        raise ValueError("UNSUPPORTED_EXECUTION_LIMITS")
    if scope.get("max_children") != 0 or scope.get("max_parallel") != 1:
        raise ValueError("PLAN_LIMIT_MISMATCH")
    nodes = workflow.get("nodes", [])
    kinds = {
        "guard",
        "read",
        "deterministic",
        "read_validate",
        "adapter",
        "verification",
        "persist",
        "outbox",
        "terminal_tick",
        "end",
    }
    ids = [node.get("id") for node in nodes]
    if (
        not ids
        or any(not isinstance(i, str) or not i for i in ids)
        or len(set(ids)) != len(ids)
    ):
        raise ValueError("INVALID_NODE_IDS")
    if set(ids) != set(EDGES):
        raise ValueError("UNSUPPORTED_NODE_IDS")
    for node in nodes:
        if node.get("kind") not in kinds:
            raise ValueError("UNSUPPORTED_NODE_TYPE")
        if set(node) - {
            "id",
            "kind",
            "on",
            "next",
            "checks",
            "routing",
            "impl",
            "rules",
        }:
            raise ValueError("UNSUPPORTED_NODE_FIELD")
        targets = list(node.get("routing", {}).values())
        if "next" in node:
            targets.append(node["next"])
        if any(target not in ids for target in targets):
            raise ValueError("DANGLING_EDGE")
        if set(targets) != EDGES[node["id"]]:
            raise ValueError("UNSUPPORTED_EDGE")
        if node.get("impl") not in (None, "hermes.execute_one_bounded_step"):
            raise ValueError("UNAUTHORIZED_EFFECT_ADAPTER")
    if digest(nodes) != NODE_CONTRACT_DIGEST:
        raise ValueError("UNSUPPORTED_NODE_CONTRACT")
    tasks = compile_tasks(plan.get("recursive_plan"))
    graph_digest = digest({"workflow": workflow, "plan_digest": actual})
    if expected_graph_digest is not None and expected_graph_digest != graph_digest:
        raise ValueError("GRAPH_DIGEST_MISMATCH")
    return CompiledWorkflow(
        plan["run_id"],
        actual,
        graph_digest,
        canonical(workflow),
        canonical(plan),
        tasks,
    )
