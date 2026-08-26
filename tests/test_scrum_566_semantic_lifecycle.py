from __future__ import annotations

import importlib
import importlib.util
import json
from pathlib import Path


def _module(name: str):
    spec = importlib.util.find_spec(name)
    assert spec is not None, f"{name} must exist"
    return importlib.import_module(name)


def _node(node_id: str, family: str) -> dict:
    return {
        "id": node_id,
        "version": "1.0.0",
        "family": family,
        "effect_class": "read_only",
        "runtime_executable": True,
        "provenance": {},
    }


def _graph() -> dict:
    return {
        "edges": [
            {
                "source": "repo_delivery.ci-run-capture",
                "target": "runtime_checkpoint.checkpoint-persist",
                "edge_type": "runtime",
                "runtime_executable": True,
            }
        ]
    }


def _event() -> dict:
    return {
        "task_id": "SCRUM-566",
        "run_id": "run-w10",
        "gate": "G2_EXECUTION",
        "scenario": "ci_failure",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "branch": "chatgpt/scrum-566-agent-runtime-corrective",
        "base_sha": "a" * 40,
        "exact_revision": "b" * 40,
        "scope_hash": "sha256:" + "c" * 64,
        "idempotency_key": "scrum-566-w10",
        "occurred_at": "2026-08-26T14:20:00Z",
        "input_payload": {"ci": "failed"},
    }


def _write_named_tool(root: Path, node_id: str) -> str:
    slug = node_id.split(".", 1)[-1].replace("-", "_")
    path = root / f"tools/node_architect/{slug}.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# semantic evaluator\n", encoding="utf-8")
    return f"tools/node_architect/{slug}.py"


def test_ordered_route_respects_runtime_edges_and_not_registry_order():
    routes = _module("tools.node_architect.gate_node_routes")
    repo = _node("repo_delivery.ci-run-capture", "repo_delivery")
    checkpoint = _node("runtime_checkpoint.checkpoint-persist", "runtime_checkpoint")
    registry_a = {"nodes": [checkpoint, repo]}
    registry_b = {"nodes": [repo, checkpoint]}

    first = routes.ordered_nodes_for_event(
        registry_a, gate="G2_EXECUTION", scenario="ci_failure", graph=_graph()
    )
    second = routes.ordered_nodes_for_event(
        registry_b, gate="G2_EXECUTION", scenario="ci_failure", graph=_graph()
    )

    assert first == ["repo_delivery.ci-run-capture", "runtime_checkpoint.checkpoint-persist"]
    assert second == first


def test_ordered_route_fails_closed_on_runtime_graph_cycle():
    routes = _module("tools.node_architect.gate_node_routes")
    repo = _node("repo_delivery.ci-run-capture", "repo_delivery")
    checkpoint = _node("runtime_checkpoint.checkpoint-persist", "runtime_checkpoint")
    graph = _graph()
    graph["edges"].append(
        {
            "source": "runtime_checkpoint.checkpoint-persist",
            "target": "repo_delivery.ci-run-capture",
            "edge_type": "runtime",
            "runtime_executable": True,
        }
    )

    try:
        routes.ordered_nodes_for_event(
            {"nodes": [repo, checkpoint]},
            gate="G2_EXECUTION",
            scenario="ci_failure",
            graph=graph,
        )
    except ValueError as exc:
        assert "ROUTE_RUNTIME_GRAPH_CYCLE" in str(exc)
    else:
        raise AssertionError("runtime graph cycle must fail closed")


def test_semantic_lifecycle_executes_entry_do_readback_exit_next_and_ledgers(tmp_path: Path):
    lifecycle = _module("tools.node_architect.semantic_lifecycle")
    dispatcher = _module("tools.node_architect.semantic_dispatcher")
    repo = _node("repo_delivery.ci-run-capture", "repo_delivery")
    checkpoint = _node("runtime_checkpoint.checkpoint-persist", "runtime_checkpoint")
    registry = {"nodes": [checkpoint, repo]}

    paths = {
        node["id"]: _write_named_tool(tmp_path, node["id"])
        for node in (repo, checkpoint)
    }
    bindings = {
        node_id: dispatcher.SemanticEvaluatorBinding(
            node_id=node_id,
            evaluator_path=path,
            handler=lambda payload, _node_id=node_id: {
                "outcome": "PASS",
                "node_id": _node_id,
                "input": dict(payload),
            },
        )
        for node_id, path in paths.items()
    }
    readbacks = {
        node_id: (lambda node, result, event, _node_id=node_id: {
            "status": "VERIFIED",
            "node_id": _node_id,
            "exact_revision": event["exact_revision"],
        })
        for node_id in paths
    }

    result = lifecycle.run_semantic_route_event(
        _event(),
        registry,
        _graph(),
        bindings=bindings,
        readback_handlers=readbacks,
        source_root=tmp_path,
        evidence_root=tmp_path / "evidence",
    )

    assert result["status"] == "SEMANTIC_ROUTE_COMPLETE"
    assert result["route_pack"] == "RP-03"
    assert result["visited_node_ids"] == [
        "repo_delivery.ci-run-capture",
        "runtime_checkpoint.checkpoint-persist",
    ]
    assert result["semantic_executed_node_ids"] == result["visited_node_ids"]
    assert all(item["semantic_result"]["semantic_execution"] for item in result["node_results"])
    assert all(item["readback"]["status"] == "VERIFIED" for item in result["node_results"])

    events_path = (
        tmp_path
        / "evidence/.gwc/tasks/SCRUM-566/node-runtime/run-w10/runtime-events.jsonl"
    )
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    assert len(events) == 12
    assert {event["event_type"] for event in events} == {
        "node-start",
        "node-decision",
        "node-result",
        "node-readback",
        "checkpoint",
        "next-route-decision",
    }


def test_semantic_lifecycle_missing_readback_fails_closed(tmp_path: Path):
    lifecycle = _module("tools.node_architect.semantic_lifecycle")
    dispatcher = _module("tools.node_architect.semantic_dispatcher")
    node = _node("repo_delivery.ci-run-capture", "repo_delivery")
    path = _write_named_tool(tmp_path, node["id"])
    binding = dispatcher.SemanticEvaluatorBinding(
        node_id=node["id"],
        evaluator_path=path,
        handler=lambda payload: {"outcome": "PASS"},
    )

    result = lifecycle.run_semantic_route_event(
        _event(),
        {"nodes": [node]},
        {"edges": []},
        bindings={node["id"]: binding},
        readback_handlers={},
        source_root=tmp_path,
        evidence_root=tmp_path / "evidence",
    )

    assert result["status"] == "SEMANTIC_ROUTE_BLOCKED"
    assert result["reason_code"] == "SEMANTIC_READBACK_UNAVAILABLE"
    assert result["visited_node_ids"] == [node["id"]]
    assert result["semantic_executed_node_ids"] == [node["id"]]


def test_semantic_lifecycle_lazy_load_stops_before_later_node(tmp_path: Path):
    lifecycle = _module("tools.node_architect.semantic_lifecycle")
    first = _node("repo_delivery.a-missing", "repo_delivery")
    second = _node("repo_delivery.z-second", "repo_delivery")
    resolved: list[str] = []

    def resolver(node, *, root):
        resolved.append(node["id"])
        return {
            "status": "DESCRIPTOR_ONLY",
            "runtime_eligible": False,
            "reason_code": "SEMANTIC_EVALUATOR_MISSING",
            "evaluator_path": None,
            "descriptor_path": None,
        }

    result = lifecycle.run_semantic_route_event(
        _event(),
        {"nodes": [second, first]},
        {"edges": []},
        bindings={},
        readback_handlers={},
        source_root=tmp_path,
        evidence_root=tmp_path / "evidence",
        source_resolver=resolver,
    )

    assert result["status"] == "SEMANTIC_ROUTE_BLOCKED"
    assert result["reason_code"] == "SEMANTIC_EVALUATOR_MISSING"
    assert resolved == ["repo_delivery.a-missing"]
    assert result["visited_node_ids"] == ["repo_delivery.a-missing"]


def test_semantic_lifecycle_replay_same_event_is_idempotent(tmp_path: Path):
    lifecycle = _module("tools.node_architect.semantic_lifecycle")
    dispatcher = _module("tools.node_architect.semantic_dispatcher")
    node = _node("repo_delivery.ci-run-capture", "repo_delivery")
    path = _write_named_tool(tmp_path, node["id"])
    binding = dispatcher.SemanticEvaluatorBinding(
        node_id=node["id"],
        evaluator_path=path,
        handler=lambda payload: {"outcome": "PASS", "input": dict(payload)},
    )
    readback = lambda node, result, event: {
        "status": "VERIFIED",
        "exact_revision": event["exact_revision"],
    }
    kwargs = {
        "bindings": {node["id"]: binding},
        "readback_handlers": {node["id"]: readback},
        "source_root": tmp_path,
        "evidence_root": tmp_path / "evidence",
    }

    first = lifecycle.run_semantic_route_event(
        _event(), {"nodes": [node]}, {"edges": []}, **kwargs
    )
    second = lifecycle.run_semantic_route_event(
        _event(), {"nodes": [node]}, {"edges": []}, **kwargs
    )

    assert second == first
    events_path = (
        tmp_path
        / "evidence/.gwc/tasks/SCRUM-566/node-runtime/run-w10/runtime-events.jsonl"
    )
    assert len(events_path.read_text(encoding="utf-8").splitlines()) == 6


def test_semantic_lifecycle_unknown_scenario_is_typed_no_route(tmp_path: Path):
    lifecycle = _module("tools.node_architect.semantic_lifecycle")
    event = _event()
    event["scenario"] = "unknown-scenario"

    result = lifecycle.run_semantic_route_event(
        event,
        {"nodes": []},
        {"edges": []},
        bindings={},
        readback_handlers={},
        source_root=tmp_path,
        evidence_root=tmp_path / "evidence",
    )

    assert result["status"] == "SEMANTIC_NO_APPLICABLE_ROUTE"
    assert result["reason_code"] == "SEMANTIC_ROUTE_UNKNOWN_SCENARIO"
