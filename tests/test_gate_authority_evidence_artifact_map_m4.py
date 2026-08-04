"""Regression tests for SCRUM-189 gate-evidence-artifact-map."""
from __future__ import annotations

import unittest

from tools.node_architect.evidence_artifact_map import build_gate_evidence_artifact_map

BASE = "1db5cdde7666e95e0a5d864633a3255a2a6ad40e"
HEAD = "f" * 40
TASK = "SCRUM-189"
COMMON = {
    "task_id": TASK,
    "repository": "nhatnguyenquang1838-coder/gwc",
    "base_sha": BASE,
    "head_sha": HEAD,
    "policy_revision": "gate-lifecycle-v1.1",
}
REQUIREMENTS = (
    ("G0_CONTEXT", "context-snapshot", f".gwc/tasks/{TASK}/g0/context-snapshot.yaml", "CANONICAL_GATE_EVIDENCE", True),
    ("G1_ALIGNMENT", "intake", f".gwc/tasks/{TASK}/g1/intake/g1-intake-brief.yaml", "CANONICAL_GATE_EVIDENCE", True),
    ("G1_ALIGNMENT", "preflight", f".gwc/tasks/{TASK}/g1/preflight/g1-preflight-report.yaml", "CANONICAL_GATE_EVIDENCE", True),
    ("G1_ALIGNMENT", "options", f".gwc/tasks/{TASK}/g1/brainstorming/g1-options.yaml", "CANONICAL_GATE_EVIDENCE", True),
    ("G1_ALIGNMENT", "decision", f".gwc/tasks/{TASK}/g1/decision/g1-decision-record.yaml", "CANONICAL_GATE_EVIDENCE", True),
    ("G2_EXECUTION", "execution-envelope", f".gwc/tasks/{TASK}/g2/execution-envelope.yaml", "CANONICAL_AUTHORITY", True),
    ("G3_PR", "delivery-record", f".gwc/tasks/{TASK}/g3/delivery-record.yaml", "DELIVERY_EVIDENCE", True),
    ("G4_MERGE", "merge-approval", f".gwc/tasks/{TASK}/g4/merge-approval.yaml", "CANONICAL_AUTHORITY", True),
)


def candidate(
    gate: str,
    role: str,
    target: str,
    classification: str,
    required: bool,
    *,
    digest_char: str = "a",
    **overrides: object,
) -> dict[str, object]:
    model: dict[str, object] = {
        "evidence_key": target,
        "gate": gate,
        "artifact_role": role,
        "artifact_type": role,
        "classification": classification,
        "required": required,
        "source_type": "repository_artifact",
        "target": target,
        "ref": target,
        "revision": HEAD if gate in {"G3_PR", "G4_MERGE", "G5_DEPLOY", "G6_PRODUCTION_DATA"} else BASE,
        "digest": "sha256:" + digest_char * 64,
        "binding_status": "BOUND",
        "freshness_status": "FRESH",
        "materialization_status": "MATERIALIZED",
        "source_of_truth": True,
    }
    model.update(overrides)
    return model


def complete_candidates() -> list[dict[str, object]]:
    return [candidate(*requirement, digest_char=hex(index + 1)[2:]) for index, requirement in enumerate(REQUIREMENTS)]


class EvidenceArtifactMapTests(unittest.TestCase):
    def test_complete_map_ready(self):
        output = build_gate_evidence_artifact_map(evidence_candidates=complete_candidates(), **COMMON)
        self.assertEqual(output["outcome"], "READY")
        self.assertIn("EVIDENCE_MAP_READY", output["reason_codes"])
        self.assertEqual(output["head_sha"], HEAD)
        self.assertFalse(output["authority_granted"])

    def test_each_entry_retains_its_candidate_digest(self):
        candidates = complete_candidates()
        output = build_gate_evidence_artifact_map(evidence_candidates=candidates, **COMMON)
        expected = {item["evidence_key"]: item["digest"] for item in candidates}
        actual = {item["evidence_key"]: item["digest"] for item in output["entries"]}
        self.assertEqual(actual, expected)
        self.assertGreater(len(set(actual.values())), 1)

    def test_order_independent_map_digest(self):
        candidates = complete_candidates()
        first = build_gate_evidence_artifact_map(evidence_candidates=candidates, **COMMON)
        second = build_gate_evidence_artifact_map(evidence_candidates=list(reversed(candidates)), **COMMON)
        self.assertEqual(first["map_digest"], second["map_digest"])

    def test_missing_required_blocks(self):
        output = build_gate_evidence_artifact_map(evidence_candidates=complete_candidates()[1:], **COMMON)
        self.assertEqual(output["outcome"], "BLOCKED")
        self.assertIn("EVIDENCE_REQUIRED_MISSING", output["reason_codes"])

    def test_stale_required_blocks(self):
        candidates = complete_candidates()
        candidates[0]["freshness_status"] = "STALE"
        output = build_gate_evidence_artifact_map(evidence_candidates=candidates, **COMMON)
        self.assertIn("EVIDENCE_STALE", output["reason_codes"])

    def test_projection_only_blocks(self):
        candidates = complete_candidates()
        candidates[0]["source_type"] = "jira_comment"
        output = build_gate_evidence_artifact_map(evidence_candidates=candidates, **COMMON)
        self.assertIn("EVIDENCE_PROJECTION_ONLY", output["reason_codes"])

    def test_head_mismatch_blocks(self):
        candidates = complete_candidates()
        g4 = next(item for item in candidates if item["gate"] == "G4_MERGE")
        g4["revision"] = BASE
        output = build_gate_evidence_artifact_map(evidence_candidates=candidates, **COMMON)
        self.assertIn("EVIDENCE_BINDING_MISMATCH", output["reason_codes"])
        self.assertIn("EVIDENCE_CI_BINDING_MISMATCH", output["reason_codes"])

    def test_wrong_canonical_role_blocks(self):
        candidates = complete_candidates()
        candidates[0]["artifact_role"] = "invented"
        output = build_gate_evidence_artifact_map(evidence_candidates=candidates, **COMMON)
        self.assertIn("EVIDENCE_BINDING_MISMATCH", output["reason_codes"])

    def test_g5_observability_incomplete_not_ci_pending(self):
        candidates = complete_candidates()
        target = "actions://g5-status-verify"
        candidates.append(candidate(
            "G5_DEPLOY",
            "status-verification",
            target,
            "DELIVERY_EVIDENCE",
            False,
            source_type="github_actions",
            materialization_status="UNOBSERVED",
            freshness_status="UNOBSERVED",
            binding_status="UNOBSERVED",
        ))
        output = build_gate_evidence_artifact_map(evidence_candidates=candidates, **COMMON)
        self.assertIn("EVIDENCE_OBSERVABILITY_INCOMPLETE", output["reason_codes"])
        self.assertNotIn("CI_PENDING", output["reason_codes"])

    def test_duplicate_conflict_blocks(self):
        candidates = complete_candidates()
        duplicate = dict(candidates[0])
        duplicate["digest"] = "sha256:" + "b" * 64
        candidates.append(duplicate)
        output = build_gate_evidence_artifact_map(evidence_candidates=candidates, **COMMON)
        self.assertIn("EVIDENCE_CONFLICT", output["reason_codes"])

    def test_invalid_digest_blocks(self):
        candidates = complete_candidates()
        candidates[0]["digest"] = "bad"
        output = build_gate_evidence_artifact_map(evidence_candidates=candidates, **COMMON)
        self.assertIn("EVIDENCE_INPUT_INVALID", output["reason_codes"])


if __name__ == "__main__":
    unittest.main()
