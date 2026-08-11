"""SCRUM-312 NA81 maturity tests for the evidence-artifact-map node.

The older SCRUM-189 tests remain compatibility coverage.  These tests bind the
current gate/action, artifact schema/freshness/presence checks, task/repository/
base/head/scope identity, drift invalidation, replay stability, and the
authority-negative boundary required by the current task.
"""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from tools.node_architect.evidence_artifact_map import build_gate_evidence_artifact_map


ROOT = Path(__file__).resolve().parents[1]
TASK = "SCRUM-312"
REPOSITORY = "nhatnguyenquang1838-coder/gwc"
BASE = "a" * 40
HEAD = "b" * 40
SCOPE = "sha256:" + "c" * 64
G2_TARGET = f".gwc/tasks/{TASK}/g2/execution-envelope.yaml"


def candidate(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "evidence_key": G2_TARGET,
        "gate": "G2_EXECUTION",
        "artifact_role": "execution-envelope",
        "artifact_type": "g2-execution-envelope",
        "classification": "CANONICAL_AUTHORITY",
        "required": True,
        "source_type": "repository_artifact",
        "target": G2_TARGET,
        "ref": G2_TARGET,
        "revision": BASE,
        "digest": "sha256:" + "d" * 64,
        "binding_status": "BOUND",
        "freshness_status": "FRESH",
        "materialization_status": "MATERIALIZED",
        "source_of_truth": True,
        "schema_valid": True,
        "availability_status": "AVAILABLE",
        "task_id": TASK,
        "repository": REPOSITORY,
        "base_sha": BASE,
        "head_sha": None,
        "scope_hash": SCOPE,
    }
    value.update(overrides)
    return value


def build(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "task_id": TASK,
        "repository": REPOSITORY,
        "base_sha": BASE,
        "head_sha": HEAD,
        "scope_hash": SCOPE,
        "current_gate": "G2_EXECUTION",
        "current_action": "modify_approved_files",
        "evidence_candidates": [candidate()],
        "policy_revision": "gate-lifecycle-v1.1",
        "mapped_at": "2026-08-11T15:30:00Z",
    }
    value.update(overrides)
    return build_gate_evidence_artifact_map(**value)


class EvidenceArtifactMapNA81Tests(unittest.TestCase):
    def test_current_gate_action_selects_exact_required_artifact_set(self):
        result = build()
        self.assertEqual(
            [(item["gate"], item["artifact_role"]) for item in result["requirements"]],
            [("G2_EXECUTION", "execution-envelope")],
        )
        self.assertEqual(result["outcome"], "READY")

    def test_schema_valid_result_and_authority_negative(self):
        result = build()
        schema = json.loads(
            (ROOT / "schemas/node-architect/gate-authority/evidence-artifact-map.schema.json")
            .read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(schema)
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(result)), [])
        self.assertIs(result["authority_granted"], False)

    def test_schema_invalid_artifact_fails_closed(self):
        result = build(evidence_candidates=[candidate(schema_valid=False)])
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("EVIDENCE_INPUT_INVALID", result["reason_codes"])

    def test_unavailable_artifact_is_typed_gap(self):
        result = build(
            evidence_candidates=[candidate(availability_status="UNAVAILABLE")]
        )
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("EVIDENCE_OBSERVABILITY_INCOMPLETE", result["reason_codes"])

    def test_identity_mismatch_fails_closed(self):
        for field, value in (
            ("task_id", "SCRUM-999"),
            ("repository", "other/repository"),
            ("base_sha", "e" * 40),
            ("scope_hash", "sha256:" + "e" * 64),
        ):
            with self.subTest(field=field):
                result = build(evidence_candidates=[candidate(**{field: value})])
                self.assertEqual(result["outcome"], "BLOCKED")
                self.assertIn("EVIDENCE_BINDING_MISMATCH", result["reason_codes"])

    def test_head_binding_and_drift_invalidate_mapping(self):
        result = build(
            current_gate="G3_PR",
            current_action="open_draft_pr",
            evidence_candidates=[
                candidate(
                    gate="G3_PR",
                    artifact_role="delivery-record",
                    artifact_type="delivery-record",
                    classification="DELIVERY_EVIDENCE",
                    target=f".gwc/tasks/{TASK}/g3/delivery-record.yaml",
                    evidence_key=f".gwc/tasks/{TASK}/g3/delivery-record.yaml",
                    ref=f".gwc/tasks/{TASK}/g3/delivery-record.yaml",
                    required=True,
                    revision=HEAD,
                    head_sha=HEAD,
                )
            ],
            observed_head_sha="e" * 40,
        )
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("EVIDENCE_BINDING_MISMATCH", result["reason_codes"])

    def test_replay_is_order_and_timestamp_stable(self):
        first = build()
        second_candidates = [copy.deepcopy(candidate())]
        second = build(
            evidence_candidates=list(reversed(second_candidates)),
            mapped_at="2026-08-12T15:30:00Z",
        )
        self.assertEqual(first["map_digest"], second["map_digest"])
        self.assertEqual(first["entries"], second["entries"])

    def test_node_has_instruction_backed_executable_route(self):
        descriptor = json.loads(
            (ROOT / "core/node-architect/node-catalog/gate_authority/evidence-artifact-map.node.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(descriptor["node_id"], "gate_authority.evidence-artifact-map")
        self.assertIn("G2_EXECUTION", descriptor["gates"])
        self.assertEqual(descriptor["authority_boundary"], "g2_required")

        profile = json.loads(
            (ROOT / "core/node-architect/gate-node-route-profile.json").read_text(
                encoding="utf-8"
            )
        )
        route = next(
            route
            for route in profile["routes"]
            if route["current_node"] == descriptor["node_id"]
        )
        self.assertEqual(route["requested_action"], "resolve_evidence_map")
        self.assertEqual(route["implementation"]["ref"], "tools/node_architect/evidence_artifact_map.py:build_gate_evidence_artifact_map")
        self.assertEqual(route["next_action"], "resolve_execution_node")


if __name__ == "__main__":
    unittest.main()
