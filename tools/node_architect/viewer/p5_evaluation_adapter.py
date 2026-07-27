#!/usr/bin/env python3
"""Render P5 evaluation and promotion records as Cytoscape elements."""
from __future__ import annotations

from typing import Any, Mapping, Sequence


PROMOTION_STAGES = [
    "experimental",
    "candidate",
    "pilot",
    "stable",
    "deprecated",
    "retired",
]


def _status_class(value: object) -> str:
    text = str(value or "unknown").lower()
    if text in {"pass", "passed", "success", "completed", "done", "replay_verified"}:
        return "p5-success"
    if text in {"warning", "partial", "degraded"}:
        return "p5-warning"
    if "human" in text or "ambiguous" in text or "waiting" in text:
        return "p5-human-required"
    if text in {"failed", "failure", "error", "stale_rejected"}:
        return "p5-failure"
    return "p5-pending"


def _metric_class(metric: Mapping[str, Any]) -> str:
    status = str(metric.get("status") or "").lower()
    if status in {"pass", "passed", "success", "met"}:
        return "metric-success"
    if status in {"warn", "warning", "partial", "degraded"}:
        return "metric-warning"
    if status in {"fail", "failed", "error"}:
        return "metric-failure"
    return "metric-pending"


def _promotion_class(stage: str, current_stage: str) -> str:
    classes = ["promotion-stage"]
    if stage == current_stage:
        classes.append("promotion-current")
    if stage in {"stable", "pilot"}:
        classes.append("promotion-active")
    if stage in {"deprecated", "retired"}:
        classes.append("promotion-inactive")
    return " ".join(classes)


def build_p5_evaluation_elements(record: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    chain_id = str(record.get("chain_id") or "")
    task_id = str(record.get("task_id") or "")
    if not chain_id:
        raise ValueError("chain_id is required")
    if not task_id:
        raise ValueError("task_id is required")

    run = dict(record.get("history", {}).get("run") or {})
    root_id = f"p5:{chain_id}"
    current_stage = str((record.get("promotion") or {}).get("current_stage") or "")
    shadow = dict(record.get("shadow") or {})
    canary = dict(shadow.get("canary") or {})
    comparison = dict(record.get("comparison") or {})
    stable = dict(comparison.get("stable") or {})
    candidate = dict(comparison.get("candidate") or {})
    replay = dict(comparison.get("replay") or {})

    nodes = [
        {
            "data": {
                "id": root_id,
                "kind": "p5-evaluation",
                "task_id": task_id,
                "chain_id": chain_id,
                "run_id": record.get("run_id"),
                "repository": record.get("repository"),
                "base_sha": record.get("base_sha"),
                "scope_hash": record.get("scope_hash"),
                "history_run_id": run.get("run_id"),
                "history_status": run.get("status"),
                "promotion_stage": current_stage,
                "provenance": "p5-evaluation-record",
            },
            "classes": f"p5-evaluation {_status_class(run.get('status'))}",
        },
        {
            "data": {
                "id": f"p5-shadow:{chain_id}",
                "kind": "shadow-planner",
                "candidate_allowed": shadow.get("candidate_allowed"),
                "confidence": shadow.get("confidence"),
                "stable_fallback": shadow.get("stable_fallback"),
                "side_effect_free": shadow.get("side_effect_free"),
                "canary_allowed": canary.get("allowed"),
                "canary_allowlisted": canary.get("allowlisted"),
                "canary_bounded": canary.get("bounded"),
                "canary_eligible": canary.get("eligible"),
                "provenance": "p5-evaluation-record",
            },
            "classes": "shadow-planner " + ("shadow-safe" if shadow.get("side_effect_free") else "shadow-risk"),
        },
        {
            "data": {
                "id": f"p5-comparison:stable:{chain_id}",
                "kind": "comparison",
                "role": "stable",
                "graph_revision": stable.get("graph_revision"),
                "route_signature": stable.get("route_signature"),
                "decision_signature": stable.get("decision_signature"),
                "provenance": "p5-evaluation-record",
            },
            "classes": "comparison stable " + _status_class(stable.get("graph_revision")),
        },
        {
            "data": {
                "id": f"p5-comparison:candidate:{chain_id}",
                "kind": "comparison",
                "role": "candidate",
                "graph_revision": candidate.get("graph_revision"),
                "route_signature": candidate.get("route_signature"),
                "decision_signature": candidate.get("decision_signature"),
                "provenance": "p5-evaluation-record",
            },
            "classes": "comparison candidate " + _status_class(candidate.get("graph_revision")),
        },
        {
            "data": {
                "id": f"p5-replay:{chain_id}",
                "kind": "replay",
                "route_matches": replay.get("route_matches"),
                "decision_matches": replay.get("decision_matches"),
                "typed_divergence": replay.get("typed_divergence"),
                "provenance": "p5-evaluation-record",
            },
            "classes": "p5-replay " + _status_class(replay.get("typed_divergence")),
        },
    ]

    edges: list[dict[str, Any]] = [
        {
            "data": {
                "id": f"p5-shadow-link:{chain_id}",
                "source": root_id,
                "target": f"p5-shadow:{chain_id}",
                "edge_type": "p5-shadow",
                "runtime_executable": False,
                "provenance": "p5-evaluation-record",
            },
            "classes": "p5-shadow visual-only",
        },
        {
            "data": {
                "id": f"p5-stable-link:{chain_id}",
                "source": root_id,
                "target": f"p5-comparison:stable:{chain_id}",
                "edge_type": "p5-comparison",
                "runtime_executable": False,
                "provenance": "p5-evaluation-record",
            },
            "classes": "p5-comparison visual-only",
        },
        {
            "data": {
                "id": f"p5-candidate-link:{chain_id}",
                "source": root_id,
                "target": f"p5-comparison:candidate:{chain_id}",
                "edge_type": "p5-comparison",
                "runtime_executable": False,
                "provenance": "p5-evaluation-record",
            },
            "classes": "p5-comparison visual-only",
        },
        {
            "data": {
                "id": f"p5-replay-link:{chain_id}",
                "source": root_id,
                "target": f"p5-replay:{chain_id}",
                "edge_type": "p5-replay",
                "runtime_executable": False,
                "provenance": "p5-evaluation-record",
            },
            "classes": "p5-replay visual-only",
        },
    ]

    for index, metric in enumerate(record.get("metrics") or []):
        metric_id = str(metric.get("metric_id") or f"metric-{index}")
        metric_node_id = f"p5-metric:{chain_id}:{metric_id}"
        nodes.append(
            {
                "data": {
                    "id": metric_node_id,
                    "kind": "metric",
                    "metric_id": metric_id,
                    "label": metric.get("label"),
                    "value": metric.get("value"),
                    "target": metric.get("target"),
                    "direction": metric.get("direction"),
                    "status": metric.get("status"),
                    "provenance": "p5-evaluation-record",
                },
                "classes": f"metric {_metric_class(metric)}",
            }
        )
        edges.append(
            {
                "data": {
                    "id": f"p5-metric-link:{chain_id}:{metric_id}",
                    "source": root_id,
                    "target": metric_node_id,
                    "edge_type": "p5-metric",
                    "runtime_executable": False,
                    "provenance": "p5-evaluation-record",
                },
                "classes": "p5-metric visual-only",
            }
        )

    promotion = dict(record.get("promotion") or {})
    previous_node_id = root_id
    for stage in promotion.get("lifecycle") or PROMOTION_STAGES:
        stage = str(stage)
        node_id = f"p5-promotion:{chain_id}:{stage}"
        nodes.append(
            {
                "data": {
                    "id": node_id,
                    "kind": "promotion-stage",
                    "stage": stage,
                    "current_stage": current_stage,
                    "human_approval_required": promotion.get("human_approval_required"),
                    "automatic_promotion": promotion.get("automatic_promotion"),
                    "rollback_plan": promotion.get("rollback_plan"),
                    "provenance": "p5-evaluation-record",
                },
                "classes": _promotion_class(stage, current_stage),
            }
        )
        edges.append(
            {
                "data": {
                    "id": f"p5-promotion-link:{chain_id}:{previous_node_id}->{stage}",
                    "source": previous_node_id,
                    "target": node_id,
                    "edge_type": "p5-promotion",
                    "runtime_executable": False,
                    "provenance": "p5-evaluation-record",
                },
                "classes": "p5-promotion visual-only",
            }
        )
        previous_node_id = node_id

    return {"nodes": nodes, "edges": edges}


def overlay_p5_evaluation(
    base_elements: Mapping[str, Sequence[Mapping[str, Any]]],
    p5_elements: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    nodes = [
        {"data": dict(element["data"]), "classes": str(element.get("classes", ""))}
        for element in base_elements.get("nodes", ())
    ]
    edges = [
        {"data": dict(element["data"]), "classes": str(element.get("classes", ""))}
        for element in base_elements.get("edges", ())
    ]
    nodes.extend(
        {"data": dict(element["data"]), "classes": str(element.get("classes", ""))}
        for element in p5_elements.get("nodes", ())
    )
    edges.extend(
        {"data": dict(element["data"]), "classes": str(element.get("classes", ""))}
        for element in p5_elements.get("edges", ())
    )
    return {"nodes": nodes, "edges": edges}

