"""Bounded orchestration projection; host adapter owns authenticated authority.

This module neither activates Hermes nor writes C/E. Injected adapters must
provide source-bound exact readback; synthetic adapters qualify mechanics only.
"""

from __future__ import annotations

import fcntl
import json
import sqlite3
from copy import deepcopy
from pathlib import Path
from typing import TypedDict

from .hermes_workflow_compiler import EDGES, canonical, digest


class GraphInvocation(TypedDict):
    context: dict


BINDING_KEYS = (
    "run_id",
    "plan_digest",
    "graph_digest",
    "thread_id",
    "host_session_id",
    "writer_id",
    "scope_digest",
    "writable_targets",
    "source_sha",
    "recipient",
)


class WorkflowRuntime:
    def __init__(self, graph, checkpoint_path, host, binding, *, backend="python"):
        self.graph, self.host, self.binding = graph, host, deepcopy(binding)
        self.path = Path(checkpoint_path).resolve()
        self._qualify(binding)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS checkpoints (thread TEXT PRIMARY KEY, binding TEXT NOT NULL, state TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS intents (key TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL)"
            )
        if backend not in ("python", "langgraph"):
            raise ValueError("UNSUPPORTED_BACKEND")
        self.backend = backend
        self.executable_graph = self._langgraph() if backend == "langgraph" else None

    def _langgraph(self):
        # Delayed optional dependency: stdlib engine remains independent.
        from langgraph.graph import END, START, StateGraph

        builder = StateGraph(GraphInvocation)

        def handler(name):
            def run(invocation):
                context = invocation["context"]
                self._step(name, context)
                return {"context": context}

            return run

        for node in self.graph.nodes:
            name = node["id"]
            builder.add_node(name, handler(name))
            if name == "end":
                builder.add_edge(name, END)
            else:
                builder.add_conditional_edges(
                    name,
                    lambda s: s["context"]["next"],
                    {target: target for target in EDGES[name]},
                )
        builder.add_edge(START, "qualify_tick")
        return builder.compile()

    def _connect(self):
        return sqlite3.connect(self.path, timeout=0.1)

    def _qualify(self, binding):
        if binding.get("qualified") is not True or binding.get("run_hold") is not False:
            raise ValueError("TICK_NOT_QUALIFIED_OR_RUN_HOLD")
        if any(
            not self.binding.get(key) or binding.get(key) != self.binding[key]
            for key in BINDING_KEYS
        ):
            raise ValueError("SESSION_RUN_WRITER_SCOPE_MISMATCH")
        if (binding["run_id"], binding["plan_digest"], binding["graph_digest"]) != (
            self.graph.run_id,
            self.graph.plan_digest,
            self.graph.graph_digest,
        ):
            raise ValueError("GRAPH_PLAN_BINDING_MISMATCH")
        if binding["scope_digest"] != digest(binding["writable_targets"]):
            raise ValueError("SCOPE_DIGEST_MISMATCH")

    def _load(self):
        with self._connect() as db:
            row = db.execute(
                "SELECT binding,state FROM checkpoints WHERE thread=?",
                (self.binding["thread_id"],),
            ).fetchone()
        if row:
            if row[0] != canonical({k: self.binding[k] for k in BINDING_KEYS}):
                raise ValueError("CHECKPOINT_BINDING_MISMATCH")
            return json.loads(row[1])
        return {
            "observed": {"controller": -1, "executor": -1},
            "consumed_controller": -1,
            "completed": {},
            "attempts": {},
            "blocked": None,
            "workflow_terminal": False,
            "authority_granted": False,
        }

    def _save(self, state):
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO checkpoints VALUES (?,?,?)",
                (
                    self.binding["thread_id"],
                    canonical({k: self.binding[k] for k in BINDING_KEYS}),
                    canonical(state),
                ),
            )

    def tick(self, binding, *, active_mission=False, max_steps=1):
        self._qualify(binding)
        if type(max_steps) is not int or not 1 <= max_steps <= 100:
            raise ValueError("INVALID_TICK_BUDGET")
        with self.path.with_suffix(".writer.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("WRITER_OVERLAP") from None
            state = self._load()
            state["trace"] = []
            context = {
                "state": state,
                "binding": deepcopy(binding),
                "command": None,
                "active": active_mission,
                "remaining": max_steps,
                "next": "qualify_tick",
            }
            if self.executable_graph is not None:
                context = self.executable_graph.invoke(
                    {"context": context},
                    config={
                        "recursion_limit": 12 * max_steps + 30,
                        "configurable": {"thread_id": binding["thread_id"]},
                    },
                )["context"]
                state = context["state"]
            else:
                while context["next"] is not None:
                    self._step(context["next"], context)
            self._save(state)
            return deepcopy(state)

    def _validate_command(self, command, cursor):
        if command.get("actor") != "CONTROLLER" or command.get("kind") not in (
            "NEXT",
            "UNLOCK",
            "RUN_HOLD",
        ):
            raise ValueError("INVALID_COMMAND_ACTOR_OR_KIND")
        if command.get("exact_readback") is not True or not command.get(
            "authority_ref"
        ):
            raise ValueError("COMMAND_NOT_EXACT")
        for key in ("run_id", "plan_digest", "thread_id", "scope_digest", "recipient"):
            if command.get(key) != self.binding[key]:
                raise ValueError("COMMAND_BINDING_MISMATCH")
        if type(command.get("seq")) is not int or command["seq"] != cursor:
            raise ValueError("COMMAND_CURSOR_MISMATCH")
        if command.get("event_digest") != digest(
            {k: v for k, v in command.items() if k != "event_digest"}
        ):
            raise ValueError("COMMAND_DIGEST_MISMATCH")
        continuation = command.get("continuation", {})
        if continuation.get("exact_readback") is not True or not continuation.get(
            "receipt_ref"
        ):
            raise ValueError("CONTINUATION_NOT_EXACT")
        if (
            any(
                continuation.get(k) != self.binding[k]
                for k in ("run_id", "thread_id", "plan_digest")
            )
            or continuation.get("controller_seq") != cursor
        ):
            raise ValueError("CONTINUATION_BINDING_MISMATCH")
        if command["kind"] == "RUN_HOLD":
            raise ValueError("RUN_HOLD")

    def _authorize(self, task):
        from fnmatch import fnmatchcase
        from pathlib import PurePosixPath

        receipt = self.host.authorize(deepcopy(self.binding), task)
        if (
            receipt.get("valid") is not True
            or receipt.get("exact_readback") is not True
            or not receipt.get("receipt_ref")
        ):
            raise ValueError("AUTHORITY_NOT_EXACT")
        if (
            any(receipt.get(k) != self.binding[k] for k in BINDING_KEYS)
            or receipt.get("task_id") != task.task_id
        ):
            raise ValueError("AUTHORITY_BINDING_MISMATCH")
        action, target = receipt.get("action"), receipt.get("target", "")
        scope = self.graph.plan["scope"]
        if (
            action not in scope["allowed_actions"]
            or action in scope["denied_actions"]
            or action not in receipt.get("allowed_actions", [])
        ):
            raise ValueError("EFFECT_NOT_AUTHORIZED")
        if (
            not target
            or PurePosixPath(target).is_absolute()
            or ".." in PurePosixPath(target).parts
            or chr(92) in target
        ):
            raise ValueError("INVALID_EFFECT_TARGET")
        if not any(
            fnmatchcase(target, pattern) for pattern in self.binding["writable_targets"]
        ):
            raise ValueError("EFFECT_SCOPE_MISMATCH")
        return receipt

    def _effect_key(self, task):
        state = self._load()
        return digest(
            {
                "binding": {k: self.binding[k] for k in BINDING_KEYS},
                "task": task.task_id,
                "attempt": state["attempts"].get(task.task_id, 0),
            }
        )

    def _once(self, kind, key, payload, effect, readback):
        # Intent is committed before any external callback. Missing readback on
        # restart is uncertainty, NOT permission to execute or send again.
        with self._connect() as db:
            row = db.execute(
                "SELECT kind,payload FROM intents WHERE key=?", (key,)
            ).fetchone()
            if row and row != (kind, canonical(payload)):
                raise ValueError("IDEMPOTENCY_PAYLOAD_MISMATCH")
            if not row:
                db.execute(
                    "INSERT INTO intents VALUES (?,?,?)",
                    (key, kind, canonical(payload)),
                )
        if not row:
            effect()
        receipt = readback(key)
        if (
            not receipt
            or receipt.get("key") != key
            or receipt.get("exact_readback") is not True
            or not receipt.get("receipt_ref")
        ):
            raise ValueError(kind + "_READBACK_UNCERTAIN")
        return receipt

    def _step(self, name, context):
        state = context["state"]
        state["trace"].append(name)
        command = context["command"]
        if name == "qualify_tick":
            self._qualify(context["binding"])
            context["next"] = "observe_ce"
        elif name == "observe_ce":
            observation = self.host.observe(
                deepcopy(self.binding), deepcopy(state["observed"])
            )
            if (
                observation.get("exact_readback") is not True
                or observation.get("source_sha") != self.binding["source_sha"]
            ):
                raise ValueError("OBSERVATION_NOT_EXACT")
            for actor in ("controller", "executor"):
                cursor = observation.get(actor + "_cursor")
                if type(cursor) is not int or cursor < state["observed"][actor]:
                    raise ValueError("CURSOR_REGRESSION")
                state["observed"][actor] = cursor
            context["observation"] = observation
            context["command"] = observation.get("command")
            context["next"] = "reconcile_state"
        elif name == "reconcile_state":
            if command is not None:
                self._validate_command(
                    command, context["observation"]["controller_cursor"]
                )
            task_index = {task.task_id: task for task in self.graph.tasks}
            for task_id, saved in state["completed"].items():
                task = task_index.get(task_id)
                if not task or not all(
                    dep in state["completed"] for dep in task.depends_on
                ):
                    raise ValueError("CHECKPOINT_EFFECT_DEPENDENCY_MISMATCH")
                observed = self.host.read_effect(self._effect_key(task))
                if (
                    observed != saved
                    or not observed
                    or observed.get("accepted") is not True
                ):
                    raise ValueError("CHECKPOINT_EFFECT_READBACK_MISMATCH")
            if state["authority_granted"] is not False or (
                state["workflow_terminal"]
                and len(state["completed"]) != len(self.graph.tasks)
            ):
                raise ValueError("CHECKPOINT_TERMINAL_OR_AUTHORITY_MISMATCH")
            context["next"] = "select_frontier"
        elif name == "select_frontier":
            if command and command["seq"] > state["consumed_controller"]:
                context["next"] = "consume_command"
            elif state["blocked"]:
                context["next"] = "evaluate_blocker"
            elif state["completed"] and len(state["completed"]) == len(
                self.graph.tasks
            ):
                context["next"] = "terminal_handoff"
            elif context["remaining"] <= 0 or not (
                context["active"] or state.get("mission")
            ):
                context["next"] = "silent_noop"
            else:
                task = next(
                    (
                        t
                        for t in self.graph.tasks
                        if t.task_id not in state["completed"]
                        and all(d in state["completed"] for d in t.depends_on)
                    ),
                    None,
                )
                context["task"] = task
                context["next"] = "precheck" if task else "evaluate_blocker"
        elif name == "consume_command":
            if state["blocked"]:
                blocked = state["blocked"]
                if (
                    command["kind"] != "UNLOCK"
                    or command.get("blocker_key") != blocked["key"]
                    or command.get("task_id") != blocked["task_id"]
                ):
                    raise ValueError("UNLOCK_BINDING_MISMATCH")
                task = next(
                    t for t in self.graph.tasks if t.task_id == blocked["task_id"]
                )
                self._authorize(task)
                if not blocked["recovery"].get("retry_safe"):
                    raise ValueError("UNLOCK_EFFECT_STILL_UNCERTAIN")
                state["attempts"][task.task_id] = (
                    state["attempts"].get(task.task_id, 0) + 1
                )
                state["blocked"] = None
            elif command["kind"] == "UNLOCK":
                raise ValueError("UNLOCK_WITHOUT_BLOCKER")
            state["consumed_controller"] = command["seq"]
            state["mission"] = True
            self._save(state)
            context["task"] = next(
                (
                    t
                    for t in self.graph.tasks
                    if t.task_id not in state["completed"]
                    and all(d in state["completed"] for d in t.depends_on)
                ),
                None,
            )
            context["next"] = "precheck"
        elif name == "precheck":
            if context.get("task") is None:
                context["next"] = "evaluate_blocker"
            else:
                self._authorize(context["task"])
                context["next"] = "execute_task"
        elif name == "execute_task":
            task = context["task"]
            key = self._effect_key(task)
            context["attempt"] = self._once(
                "EFFECT",
                key,
                {"task_id": task.task_id},
                lambda: self.host.execute(task, key),
                self.host.read_effect,
            )
            context["remaining"] -= 1
            context["next"] = "verify_task"
        elif name == "verify_task":
            task = context["task"]
            receipt = self.host.read_effect(self._effect_key(task))
            if (
                not receipt
                or receipt.get("key") != self._effect_key(task)
                or receipt.get("task_id") != task.task_id
                or receipt.get("exact_readback") is not True
                or not receipt.get("receipt_ref")
            ):
                raise ValueError("EFFECT_READBACK_UNCERTAIN")
            context["receipt"] = receipt
            context["next"] = (
                "persist_progress"
                if receipt.get("accepted") is True
                else "evaluate_blocker"
            )
        elif name == "persist_progress":
            state["completed"][context["task"].task_id] = context["receipt"]
            self._save(state)
            context["next"] = "select_frontier"
        elif name == "terminal_handoff":
            if not state["workflow_terminal"]:
                key = digest(
                    {
                        "thread": self.binding["thread_id"],
                        "graph": self.graph.graph_digest,
                        "kind": "TASK_TERMINAL",
                    }
                )
                receipt = self._once(
                    "TASK_TERMINAL",
                    key,
                    state["completed"],
                    lambda: self.host.handoff(
                        "TASK_TERMINAL", deepcopy(state["completed"]), key
                    ),
                    self.host.read_delivery,
                )
                if (
                    not receipt
                    or receipt.get("key") != key
                    or receipt.get("exact_readback") is not True
                    or receipt.get("delivered") is not True
                ):
                    raise ValueError("DELIVERY_UNCERTAIN")
                state["workflow_terminal"] = True
                self._save(state)
            context["next"] = "end"
        elif name == "evaluate_blocker":
            if state["blocked"]:
                context["next"] = "deadlock_handoff"
                return
            task = context.get("task")
            recovery = self.host.recover(task) if task else {}
            genuine = (
                recovery.get("performed") is True
                and recovery.get("exact_readback") is True
                and bool(recovery.get("receipt_ref"))
            )
            other_frontier = (
                any(
                    t.task_id != task.task_id
                    and t.task_id not in state["completed"]
                    and all(d in state["completed"] for d in t.depends_on)
                    for t in self.graph.tasks
                )
                if task
                else False
            )
            if (
                genuine
                and recovery.get("legal_next") is True
                and recovery.get("retry_safe") is True
            ):
                state["attempts"][task.task_id] = (
                    state["attempts"].get(task.task_id, 0) + 1
                )
            elif (
                genuine
                and recovery.get("legal_next") is False
                and not other_frontier
                and recovery.get("owner") == "CONTROLLER"
                and recovery.get("release_trigger")
                and 2 <= len(recovery.get("alternatives", [])) <= 3
            ):
                payload = {
                    "run_id": self.graph.run_id,
                    "thread_id": self.binding["thread_id"],
                    "task_id": task.task_id,
                    "consumed_seq": state["consumed_controller"],
                    "failure_signature": context["receipt"].get("failure_signature"),
                    "recovery": recovery,
                }
                payload["key"] = digest(payload)
                state["blocked"] = payload
            self._save(state)
            context["next"] = "deadlock_handoff" if state["blocked"] else "silent_noop"
        elif name == "deadlock_handoff":
            blocked = state["blocked"]
            receipt = self._once(
                "VERIFIED_DEADLOCK_UNLOCK",
                blocked["key"],
                blocked,
                lambda: self.host.handoff(
                    "VERIFIED_DEADLOCK_UNLOCK", deepcopy(blocked), blocked["key"]
                ),
                self.host.read_delivery,
            )
            if (
                receipt.get("delivered") is not True
                or receipt.get("kind") != "VERIFIED_DEADLOCK_UNLOCK"
            ):
                raise ValueError("DELIVERY_UNCERTAIN")
            state["deadlock_delivery"] = receipt
            context["next"] = "silent_noop"
        elif name == "silent_noop":
            context["next"] = "end"
        elif name == "end":
            context["next"] = None
        else:
            raise ValueError("UNSUPPORTED_RUNTIME_NODE")
        if name != "end" and context["next"] not in EDGES[name]:
            raise ValueError("RUNTIME_EDGE_NOT_COMPILED")
