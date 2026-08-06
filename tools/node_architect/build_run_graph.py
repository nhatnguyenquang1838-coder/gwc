#!/usr/bin/env python3
"""Build a deterministic, run-scoped Node Architect graph from canonical events.

The graph contains only participants that actually emitted events for the run.
Gate actions are represented explicitly and are never promoted to fake catalogue
node IDs. The module is pure: no network, repository, Jira, PR, merge, deploy, or
production side effect is performed.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

GATES = (
    "G0_CONTEXT", "G1_ALIGNMENT", "G2_EXECUTION", "G3_PR",
    "G4_MERGE", "G5_DEPLOY", "G6_PRODUCTION_DATA",
)
PARTICIPANT_TYPES = {"runtime_node", "gate_action"}
EDGE_TYPES = {"runtime", "recovery", "authority", "visualization"}
STATUSES = {"executed", "passed", "blocked", "not_executed", "not_applicable"}
SHA40 = re.compile(r"^[0-9a-f]{40}$")


class RunGraphError(ValueError):
    """Fail-closed graph construction error with a stable reason code."""

    def __init__(self, reason_code: str, message: str):
        super().__init__(f"{reason_code}: {message}")
        self.reason_code = reason_code
        self.message = message


def _canonical_digest(value: Mapping[str, Any], digest_field: str) -> str:
    semantic = {key: item for key, item in value.items() if key != digest_field}
    payload = json.dumps(semantic, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _require_string(value: Mapping[str, Any], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item.strip():
        raise RunGraphError("AUTONOMOUS_GRAPH_INPUT_INVALID", f"{field} must be a non-empty string")
    return item.strip()


def _string_list(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise RunGraphError("AUTONOMOUS_GRAPH_INPUT_INVALID", f"{field} must be an array of non-empty strings")
    return sorted(set(item.strip() for item in value))


def _validate_identity(run: Mapping[str, Any]) -> None:
    for field in ("run_id", "task_id", "repository", "base_ref", "head_ref", "graph_revision"):
        _require_string(run, field)
    for field in ("base_sha", "head_sha"):
        value = _require_string(run, field)
        if not SHA40.fullmatch(value):
            raise RunGraphError("AUTONOMOUS_GRAPH_INPUT_INVALID", f"{field} must be a lowercase 40-character SHA")
    repository = str(run["repository"])
    if repository.count("/") != 1 or any(part.strip() != part or not part for part in repository.split("/")):
        raise RunGraphError("AUTONOMOUS_GRAPH_INPUT_INVALID", "repository must use owner/name form")


def _validate_events(events: Any) -> list[dict[str, Any]]:
    if not isinstance(events, list) or not events:
        raise RunGraphError("AUTONOMOUS_GRAPH_EVENT_MISSING", "events must contain at least one canonical runtime event")
    normalized: list[dict[str, Any]] = []
    event_ids: set[str] = set()
    sequences: set[int] = set()
    for index, raw in enumerate(events):
        if not isinstance(raw, Mapping):
            raise RunGraphError("AUTONOMOUS_GRAPH_INPUT_INVALID", f"events[{index}] must be an object")
        event = dict(raw)
        event_id = _require_string(event, "event_id")
        if event_id in event_ids:
            raise RunGraphError("AUTONOMOUS_GRAPH_EVENT_DUPLICATE", f"duplicate event_id {event_id}")
        event_ids.add(event_id)
        sequence = event.get("sequence")
        if not isinstance(sequence, int) or sequence < 0:
            raise RunGraphError("AUTONOMOUS_GRAPH_INPUT_INVALID", f"events[{index}].sequence must be a non-negative integer")
        if sequence in sequences:
            raise RunGraphError("AUTONOMOUS_GRAPH_EVENT_DUPLICATE", f"duplicate event sequence {sequence}")
        sequences.add(sequence)
        gate = _require_string(event, "gate")
        if gate not in GATES:
            raise RunGraphError("AUTONOMOUS_GRAPH_INPUT_INVALID", f"unsupported gate {gate}")
        participant_type = _require_string(event, "participant_type")
        if participant_type not in PARTICIPANT_TYPES:
            raise RunGraphError("AUTONOMOUS_GRAPH_INPUT_INVALID", f"unsupported participant_type {participant_type}")
        status = _require_string(event, "status")
        if status not in STATUSES:
            raise RunGraphError("AUTONOMOUS_GRAPH_INPUT_INVALID", f"unsupported event status {status}")
        edge_type = event.get("edge_type", "runtime")
        if edge_type not in EDGE_TYPES:
            raise RunGraphError("AUTONOMOUS_GRAPH_INPUT_INVALID", f"unsupported edge_type {edge_type}")
        event["participant_id"] = _require_string(event, "participant_id")
        event["purpose"] = _require_string(event, "purpose")
        event["action"] = _require_string(event, "action")
        event["outcome"] = _require_string(event, "outcome")
        event["entry_evidence"] = _string_list(event.get("entry_evidence"), f"events[{index}].entry_evidence")
        event["evidence_refs"] = _string_list(event.get("evidence_refs"), f"events[{index}].evidence_refs")
        event["edge_type"] = edge_type
        next_event_id = event.get("next_event_id")
        if next_event_id is not None and (not isinstance(next_event_id, str) or not next_event_id.strip()):
            raise RunGraphError("AUTONOMOUS_GRAPH_INPUT_INVALID", f"events[{index}].next_event_id must be null or a non-empty string")
        event["next_event_id"] = next_event_id.strip() if isinstance(next_event_id, str) else None
        provenance = event.get("route_provenance") or f"event:{event_id}"
        if not isinstance(provenance, str) or not provenance.strip():
            raise RunGraphError("AUTONOMOUS_GRAPH_INPUT_INVALID", f"events[{index}].route_provenance must be a non-empty string")
        event["route_provenance"] = provenance.strip()
        normalized.append(event)
    normalized.sort(key=lambda item: item["sequence"])
    known = {item["event_id"] for item in normalized}
    for event in normalized:
        if event["next_event_id"] and event["next_event_id"] not in known:
            raise RunGraphError("AUTONOMOUS_GRAPH_ROUTE_TARGET_MISSING", f"event {event['event_id']} routes to unknown event {event['next_event_id']}")
    return normalized


def build_run_graph(run: Mapping[str, Any]) -> dict[str, Any]:
    """Return a canonical graph bound to one run and exact repository head."""
    if not isinstance(run, Mapping):
        raise RunGraphError("AUTONOMOUS_GRAPH_INPUT_INVALID", "run input must be an object")
    _validate_identity(run)
    events = _validate_events(run.get("events"))
    instance_for_event = {event["event_id"]: f"event-{event['sequence']:04d}" for event in events}
    nodes: list[dict[str, Any]] = []
    for event in events:
        next_route = event["next_event_id"]
        nodes.append({
            "instance_id": instance_for_event[event["event_id"]],
            "canonical_id": event["participant_id"],
            "participant_type": event["participant_type"],
            "gate": event["gate"],
            "sequence": event["sequence"],
            "purpose": event["purpose"],
            "status": event["status"],
            "entry_evidence": event["entry_evidence"],
            "action": event["action"],
            "outcome": event["outcome"],
            "output_evidence": event["evidence_refs"],
            "next_route": instance_for_event[next_route] if next_route else None,
        })
    edges: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        target_event_id = event["next_event_id"]
        if target_event_id is None and index + 1 < len(events):
            target_event_id = events[index + 1]["event_id"]
        if target_event_id is None:
            continue
        edge_type = event["edge_type"]
        edges.append({
            "edge_id": f"edge-{event['sequence']:04d}-{instance_for_event[target_event_id]}",
            "source": instance_for_event[event["event_id"]],
            "target": instance_for_event[target_event_id],
            "edge_type": edge_type,
            "runtime_executable": edge_type in {"runtime", "recovery", "authority"},
            "provenance": event["route_provenance"],
            "sequence": event["sequence"],
        })
    statuses = {node["status"] for node in nodes}
    terminal_status = "BLOCKED" if "blocked" in statuses else "PASS" if nodes[-1]["status"] in {"passed", "executed", "not_applicable"} else "INCOMPLETE"
    graph: dict[str, Any] = {
        "schema_version": "1.0", "artifact_type": "autonomous-run-graph",
        "run_id": str(run["run_id"]), "task_id": str(run["task_id"]), "repository": str(run["repository"]),
        "base_ref": str(run["base_ref"]), "base_sha": str(run["base_sha"]),
        "head_ref": str(run["head_ref"]), "head_sha": str(run["head_sha"]),
        "graph_revision": str(run["graph_revision"]), "nodes": nodes, "edges": edges,
        "terminal_status": terminal_status,
    }
    graph["graph_digest"] = _canonical_digest(graph, "graph_digest")
    return graph


def _mermaid_id(instance_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", instance_id)


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', "'").replace("\n", " ")


def render_mermaid(graph: Mapping[str, Any]) -> str:
    """Render a deterministic Mermaid projection from canonical graph JSON."""
    lines = ["flowchart TD"]
    for node in graph.get("nodes", []):
        mermaid_id = _mermaid_id(str(node["instance_id"]))
        label = _escape_label(f"{node['gate']} · {node['canonical_id']}<br/>{node['outcome']}")
        if node["participant_type"] == "gate_action":
            lines.append(f'  {mermaid_id}{{"{label}"}}')
        else:
            lines.append(f'  {mermaid_id}["{label}"]')
    arrow = {"runtime": "-->", "recovery": "-.->", "authority": "==>", "visualization": "-.-"}
    for edge in graph.get("edges", []):
        source = _mermaid_id(str(edge["source"]))
        target = _mermaid_id(str(edge["target"]))
        label = _escape_label(f"{edge['edge_type']} · {edge['provenance']}")
        lines.append(f"  {source} {arrow[edge['edge_type']]}|{label}| {target}")
    return "\n".join(lines) + "\n"


__all__ = ["GATES", "RunGraphError", "build_run_graph", "render_mermaid"]
