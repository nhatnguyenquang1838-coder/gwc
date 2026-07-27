#!/usr/bin/env python3
"""Convert durable run/event/checkpoint history into Cytoscape elements."""
from __future__ import annotations
from typing import Any, Mapping, Sequence


def _status_class(value: object) -> str:
    text = str(value or "unknown").lower()
    if text in {"pass", "passed", "success", "completed", "done", "replay_verified"}:
        return "history-success"
    if "human" in text or "ambiguous" in text or "waiting" in text:
        return "history-human-required"
    if text in {"failed", "failure", "error", "stale_rejected"}:
        return "history-failure"
    return "history-pending"


def build_run_history_elements(
    history: Mapping[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    run = dict(history.get("run") or {})
    run_id = str(run.get("run_id") or "")
    if not run_id:
        raise ValueError("run.run_id is required")

    nodes = [
        {
            "data": {
                "id": f"run:{run_id}",
                "kind": "run",
                "run_id": run_id,
                "task_id": run.get("task_id"),
                "repository": run.get("repository"),
                "base_sha": run.get("base_sha"),
                "scope_hash": run.get("scope_hash"),
                "graph_revision": run.get("graph_revision"),
                "status": run.get("status"),
                "provenance": "durable-run-history",
            },
            "classes": f"run-history {_status_class(run.get('status'))}",
        }
    ]
    edges = []
    previous = f"run:{run_id}"

    for index, event_value in enumerate(history.get("events") or []):
        event = dict(event_value)
        event_id = str(event.get("event_id") or f"event-{index}")
        node_id = f"event:{run_id}:{event_id}"
        nodes.append(
            {
                "data": {
                    "id": node_id,
                    "kind": "event",
                    "event_id": event_id,
                    "run_id": run_id,
                    "sequence": event.get("sequence", index),
                    "event_type": event.get("event_type"),
                    "node_id": event.get("node_id"),
                    "gate": event.get("gate"),
                    "outcome": event.get("outcome"),
                    "timestamp": event.get("timestamp"),
                    "evidence": event.get("evidence", []),
                    "provenance": "durable-event-history",
                },
                "classes": f"run-event {_status_class(event.get('outcome'))}",
            }
        )
        edges.append(
            {
                "data": {
                    "id": f"history-order:{run_id}:{index}",
                    "source": previous,
                    "target": node_id,
                    "edge_type": "history-order",
                    "runtime_executable": False,
                    "provenance": "durable-run-history",
                },
                "classes": "history-order visual-only",
            }
        )
        if event.get("node_id"):
            edges.append(
                {
                    "data": {
                        "id": f"history-node:{run_id}:{event_id}",
                        "source": node_id,
                        "target": str(event["node_id"]),
                        "edge_type": "history-observed-node",
                        "runtime_executable": False,
                        "provenance": "durable-run-history",
                    },
                    "classes": "history-observed-node visual-only",
                }
            )
        previous = node_id

    for index, checkpoint_value in enumerate(history.get("checkpoints") or []):
        checkpoint = dict(checkpoint_value)
        revision = int(checkpoint.get("revision", index))
        checkpoint_id = f"checkpoint:{run_id}:{revision}"
        nodes.append(
            {
                "data": {
                    "id": checkpoint_id,
                    "kind": "checkpoint",
                    "run_id": run_id,
                    "revision": revision,
                    "current_node_id": checkpoint.get("current_node_id"),
                    "next_node_id": checkpoint.get("next_node_id"),
                    "next_action": checkpoint.get("next_action"),
                    "gate": checkpoint.get("gate"),
                    "status": checkpoint.get("status"),
                    "lease_owner": checkpoint.get("lease_owner"),
                    "fencing_token": checkpoint.get("fencing_token"),
                    "pending_actions": checkpoint.get("pending_actions", []),
                    "evidence": checkpoint.get("evidence", []),
                    "provenance": "durable-checkpoint-history",
                },
                "classes": f"run-checkpoint {_status_class(checkpoint.get('status'))}",
            }
        )
        edges.append(
            {
                "data": {
                    "id": f"history-checkpoint:{run_id}:{revision}",
                    "source": f"run:{run_id}",
                    "target": checkpoint_id,
                    "edge_type": "history-checkpoint",
                    "runtime_executable": False,
                    "provenance": "durable-run-history",
                },
                "classes": "history-checkpoint visual-only",
            }
        )
        if checkpoint.get("current_node_id"):
            edges.append(
                {
                    "data": {
                        "id": f"checkpoint-node:{run_id}:{revision}",
                        "source": checkpoint_id,
                        "target": str(checkpoint["current_node_id"]),
                        "edge_type": "history-observed-node",
                        "runtime_executable": False,
                        "provenance": "durable-run-history",
                    },
                    "classes": "history-observed-node visual-only",
                }
            )
    return {"nodes": nodes, "edges": edges}


def overlay_run_history(
    base_elements: Mapping[str, Sequence[Mapping[str, Any]]],
    history_elements: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    nodes = [
        {"data": dict(element["data"]), "classes": str(element.get("classes", ""))}
        for element in base_elements.get("nodes", ())
    ]
    edges = [
        {"data": dict(element["data"]), "classes": str(element.get("classes", ""))}
        for element in base_elements.get("edges", ())
    ]
    observed = {
        edge["data"]["target"]
        for edge in history_elements.get("edges", ())
        if edge.get("data", {}).get("edge_type") == "history-observed-node"
    }
    for node in nodes:
        if node["data"].get("id") in observed and "history-observed" not in node["classes"].split():
            node["classes"] = (node["classes"] + " history-observed").strip()
    nodes.extend(
        {"data": dict(element["data"]), "classes": str(element.get("classes", ""))}
        for element in history_elements.get("nodes", ())
    )
    edges.extend(
        {"data": dict(element["data"]), "classes": str(element.get("classes", ""))}
        for element in history_elements.get("edges", ())
    )
    return {"nodes": nodes, "edges": edges}
