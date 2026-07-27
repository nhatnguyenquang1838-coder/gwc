from __future__ import annotations

import unittest

from tools.node_architect.viewer.p5_evaluation_adapter import (
    build_p5_evaluation_elements,
)
from tools.node_architect.viewer.registry_adapter import build_cytoscape_elements
from tools.validate_p5_evaluation import validate_record


GOOD_RECORD = {
    "schema_version": "0.1",
    "task_id": "SCRUM-122",
    "chain_id": "SCRUM-122-126",
    "linked_task_ids": ["SCRUM-122", "SCRUM-123", "SCRUM-124", "SCRUM-125", "SCRUM-126"],
    "repository": "nhatnguyenquang1838-coder/gwc",
    "base_sha": "cd9b49cf9e6fd97413bc49ed480b2fc9941513af",
    "scope_hash": "sha256:" + "9" * 64,
    "run_id": "p5-eval-122-126-20260727",
    "history": {
        "run": {"run_id": "p5-eval-122-126-20260727", "status": "completed"},
        "events": [],
        "checkpoints": [],
    },
    "metrics": [
        {
            "metric_id": "catalog-quality",
            "label": "Catalog quality",
            "value": 1.0,
            "target": 1.0,
            "direction": "higher_is_better",
            "status": "pass",
        },
        {
            "metric_id": "confidence-calibration",
            "label": "Confidence calibration",
            "value": 0.92,
            "target": 0.8,
            "direction": "higher_is_better",
            "status": "pass",
        },
        {
            "metric_id": "evidence-completeness",
            "label": "Evidence completeness",
            "value": 1.0,
            "target": 1.0,
            "direction": "higher_is_better",
            "status": "pass",
        },
        {
            "metric_id": "human-override-rate",
            "label": "Human override rate",
            "value": 0.0,
            "target": 0.1,
            "direction": "lower_is_better",
            "status": "pass",
        },
        {
            "metric_id": "outcome-comparison-accuracy",
            "label": "Outcome comparison accuracy",
            "value": 1.0,
            "target": 0.9,
            "direction": "higher_is_better",
            "status": "pass",
        },
        {
            "metric_id": "planning-completeness",
            "label": "Planning completeness",
            "value": 1.0,
            "target": 0.9,
            "direction": "higher_is_better",
            "status": "pass",
        },
        {
            "metric_id": "policy-violation-rate",
            "label": "Policy violation rate",
            "value": 0.0,
            "target": 0.0,
            "direction": "lower_is_better",
            "status": "pass",
        },
        {
            "metric_id": "recovery-success-rate",
            "label": "Recovery success rate",
            "value": 1.0,
            "target": 0.9,
            "direction": "higher_is_better",
            "status": "pass",
        },
        {
            "metric_id": "route-selection-accuracy",
            "label": "Route selection accuracy",
            "value": 1.0,
            "target": 0.9,
            "direction": "higher_is_better",
            "status": "pass",
        },
        {
            "metric_id": "runtime-history-completeness",
            "label": "Runtime history completeness",
            "value": 1.0,
            "target": 0.9,
            "direction": "higher_is_better",
            "status": "pass",
        },
    ],
    "shadow": {
        "candidate_allowed": True,
        "confidence": 0.92,
        "stable_fallback": True,
        "side_effect_free": True,
        "canary": {
            "allowed": True,
            "allowlisted": True,
            "bounded": True,
            "eligible": True,
        },
    },
    "comparison": {
        "stable": {
            "graph_revision": "stable-r1",
            "route_signature": "stable-route",
            "decision_signature": "stable-decision",
        },
        "candidate": {
            "graph_revision": "candidate-r1",
            "route_signature": "candidate-route",
            "decision_signature": "candidate-decision",
        },
        "replay": {
            "route_matches": True,
            "decision_matches": True,
        },
    },
    "promotion": {
        "lifecycle": [
            "experimental",
            "candidate",
            "pilot",
            "stable",
            "deprecated",
            "retired",
        ],
        "current_stage": "pilot",
        "human_approval_required": True,
        "automatic_promotion": False,
        "rollback_plan": "revert to stable planner and prior graph revision",
    },
    "projections": [
        {"system": "jira", "authority": "projection", "grants_gate_authority": False},
    ],
}


class P5EvaluationAdapterTests(unittest.TestCase):
    def test_validator_accepts_the_bounded_record(self) -> None:
        self.assertEqual([], validate_record(GOOD_RECORD))

    def test_validator_rejects_production_like_promotion(self) -> None:
        bad = dict(GOOD_RECORD, promotion=dict(GOOD_RECORD["promotion"], automatic_promotion=True))
        codes = {item["code"] for item in validate_record(bad)}
        self.assertIn("PROMOTION_POLICY_VIOLATION", codes)

    def test_validator_rejects_projection_authority_leakage(self) -> None:
        bad = dict(
            GOOD_RECORD,
            projections=[{"system": "jira", "authority": "projection", "grants_gate_authority": True}],
        )
        codes = {item["code"] for item in validate_record(bad)}
        self.assertIn("PROJECTION_AUTHORITY_LEAKAGE", codes)

    def test_overlay_renders_visual_only_p5_nodes_and_edges(self) -> None:
        elements = build_p5_evaluation_elements(GOOD_RECORD)
        node_ids = {node["data"]["id"] for node in elements["nodes"]}
        edge_ids = {edge["data"]["id"] for edge in elements["edges"]}

        self.assertIn("p5:SCRUM-122-126", node_ids)
        self.assertTrue(any(node_id.startswith("p5-metric:SCRUM-122-126:") for node_id in node_ids))
        self.assertTrue(any(node_id.startswith("p5-promotion:SCRUM-122-126:") for node_id in node_ids))
        self.assertTrue(all(edge["data"]["runtime_executable"] is False for edge in elements["edges"]))
        self.assertTrue(any(edge_id.startswith("p5-promotion-link:") for edge_id in edge_ids))

    def test_registry_adapter_accepts_p5_overlay(self) -> None:
        bundle = {
            "nodes": {
                "nodes": [
                    {
                        "id": "repo_delivery.ci-run-capture",
                        "family": "repo_delivery",
                        "maturity": "implemented",
                        "source_status": "implemented",
                        "provenance": "test",
                    },
                    {
                        "id": "validation_quality.ci-evidence-capture",
                        "family": "validation_quality",
                        "maturity": "implemented",
                        "source_status": "implemented",
                        "provenance": "test",
                    },
                ]
            },
            "graph": {"edges": []},
        }

        elements = build_cytoscape_elements(bundle, p5_evaluation=GOOD_RECORD)
        self.assertTrue(any(node["data"].get("kind") == "p5-evaluation" for node in elements["nodes"]))
        self.assertTrue(
            all(
                not edge["data"]["runtime_executable"]
                for edge in elements["edges"]
                if str(edge["data"].get("edge_type", "")).startswith("p5-")
            )
        )


if __name__ == "__main__":
    unittest.main()

