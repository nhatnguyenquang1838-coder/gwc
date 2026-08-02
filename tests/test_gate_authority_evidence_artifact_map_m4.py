"""RED->GREEN tests for SCRUM-189 gate-evidence-artifact-map (MAT-F2-N06).

Covers the canonical evidence boundary defined in the issue:
  * complete G0-G6 mapping;
  * projection-only evidence rejected as canonical;
  * missing / stale required artifacts;
  * exact-head mismatch;
  * G5 PR-filtered empty -> observability incomplete (not CI pending);
  * G6 not-applicable when no G6 candidate;
  * duplicate evidence keys with conflicting digests block the map;
  * equivalent candidates yield the same map digest regardless of order.

Run: python -m unittest tests.test_gate_authority_evidence_artifact_map_m4 -v
"""

import unittest

from tools.node_architect.evidence_artifact_map import build_gate_evidence_artifact_map

_BASE = dict(
    task_id="SCRUM-189",
    repository="nhatnguyenquang1838-coder/gwc",
    base_sha="1db5cdde7666e95e0a5d864633a3255a2a6ad40e",
    policy_revision="gate-lifecycle-v1.1",
)

def _candidate(key, gate, target, **over):
    c = dict(
        evidence_key=key,
        gate=gate,
        artifact_role="ctx",
        artifact_type="yaml",
        classification="CANONICAL_GATE_EVIDENCE",
        required=True,
        source_type="filesystem",
        target=target,
        ref="main",
        revision="1db5cdde7666e95e0a5d864633a3255a2a6ad40e",
        digest="sha256:" + "a" * 64,
        binding_status="BOUND",
        freshness_status="FRESH",
        materialization_status="MATERIALIZED",
        source_of_truth=True,
    )
    c.update(over)
    return c


class EvidenceArtifactMapTests(unittest.TestCase):
    # --- Happy path -------------------------------------------------------
    def test_complete_map_ready(self):
        cands = [
            _candidate("g0", "G0_CONTEXT", ".gwc/tasks/SCRUM-189/g0/context-snapshot.yaml"),
            _candidate("g1-intake", "G1_ALIGNMENT", ".gwc/tasks/SCRUM-189/g1/intake/g1-intake-brief.yaml"),
            _candidate("g1-preflight", "G1_ALIGNMENT", ".gwc/tasks/SCRUM-189/g1/preflight/g1-preflight-report.yaml"),
            _candidate("g1-options", "G1_ALIGNMENT", ".gwc/tasks/SCRUM-189/g1/brainstorming/g1-options.yaml"),
            _candidate("g1-decision", "G1_ALIGNMENT", ".gwc/tasks/SCRUM-189/g1/decision/g1-decision-record.yaml"),
            _candidate("g2", "G2_EXECUTION", ".gwc/tasks/SCRUM-189/g2/execution-envelope.yaml",
                       classification="CANONICAL_AUTHORITY"),
            _candidate("g3", "G3_PR", ".gwc/tasks/SCRUM-189/g3/delivery-record.yaml",
                       classification="DELIVERY_EVIDENCE"),
            _candidate("g4", "G4_MERGE", ".gwc/tasks/SCRUM-189/g4/merge-approval.yaml",
                       classification="CANONICAL_AUTHORITY"),
        ]
        out = build_gate_evidence_artifact_map(evidence_candidates=cands, **_BASE)
        self.assertEqual(out["outcome"], "READY")
        self.assertIn("EVIDENCE_MAP_READY", out["reason_codes"])
        self.assertEqual(out["missing_required"], [])
        self.assertFalse(out["authority_granted"])

    def test_order_independent_digest(self):
        cands = [
            _candidate("g0", "G0_CONTEXT", ".gwc/tasks/SCRUM-189/g0/context-snapshot.yaml"),
            _candidate("g2", "G2_EXECUTION", ".gwc/tasks/SCRUM-189/g2/execution-envelope.yaml",
                       classification="CANONICAL_AUTHORITY"),
        ]
        a = build_gate_evidence_artifact_map(evidence_candidates=list(reversed(cands)), **_BASE)
        b = build_gate_evidence_artifact_map(evidence_candidates=cands, **_BASE)
        self.assertEqual(a["map_digest"], b["map_digest"])

    # --- Fail-closed ------------------------------------------------------
    def test_missing_required_blocks(self):
        cands = [_candidate("g0", "G0_CONTEXT", ".gwc/tasks/SCRUM-189/g0/context-snapshot.yaml")]
        out = build_gate_evidence_artifact_map(evidence_candidates=cands, **_BASE)
        self.assertEqual(out["outcome"], "BLOCKED")
        self.assertIn("EVIDENCE_REQUIRED_MISSING", out["reason_codes"])
        self.assertTrue(out["missing_required"])

    def test_stale_required_blocks(self):
        cands = [
            _candidate("g0", "G0_CONTEXT", ".gwc/tasks/SCRUM-189/g0/context-snapshot.yaml",
                       freshness_status="STALE"),
            _candidate("g2", "G2_EXECUTION", ".gwc/tasks/SCRUM-189/g2/execution-envelope.yaml",
                       classification="CANONICAL_AUTHORITY", freshness_status="STALE"),
        ]
        out = build_gate_evidence_artifact_map(evidence_candidates=cands, **_BASE)
        self.assertEqual(out["outcome"], "BLOCKED")
        self.assertIn("EVIDENCE_STALE", out["reason_codes"])
        self.assertTrue(out["stale_required"])

    def test_projection_only_blocks(self):
        cands = [
            _candidate("g0", "G0_CONTEXT", ".gwc/tasks/SCRUM-189/g0/context-snapshot.yaml",
                       source_type="jira_comment", source_of_truth=True),
        ]
        out = build_gate_evidence_artifact_map(evidence_candidates=cands, **_BASE)
        self.assertEqual(out["outcome"], "BLOCKED")
        self.assertIn("EVIDENCE_PROJECTION_ONLY", out["reason_codes"])

    def test_head_mismatch_blocks(self):
        cands = [
            _candidate("g4", "G4_MERGE", ".gwc/tasks/SCRUM-189/g4/merge-approval.yaml",
                       classification="CANONICAL_AUTHORITY",
                       revision="deadbeef" * 5, binding_status="MISMATCHED"),
        ]
        out = build_gate_evidence_artifact_map(evidence_candidates=cands, **_BASE)
        self.assertIn("EVIDENCE_BINDING_MISMATCH", out["reason_codes"])
        self.assertIn("EVIDENCE_CI_BINDING_MISMATCH", out["reason_codes"])

    def test_g5_observability_incomplete_not_ci_pending(self):
        # G5 PR-filtered empty result (no materialization, no error) -> observability
        # incomplete, NOT CI pending.
        cands = [
            _candidate("g0", "G0_CONTEXT", ".gwc/tasks/SCRUM-189/g0/context-snapshot.yaml"),
            _candidate("g5", "G5_DEPLOY", ".gwc/tasks/SCRUM-189/g5/deployment-approval.yaml",
                       classification="CANONICAL_AUTHORITY",
                       materialization_status="UNOBSERVED", freshness_status="UNOBSERVED",
                       binding_status="UNOBSERVED"),
        ]
        out = build_gate_evidence_artifact_map(evidence_candidates=cands, **_BASE)
        self.assertIn("EVIDENCE_OBSERVABILITY_INCOMPLETE", out["reason_codes"])
        self.assertNotIn("CI_PENDING", out["reason_codes"])

    def test_g6_not_applicable(self):
        cands = [_candidate("g0", "G0_CONTEXT", ".gwc/tasks/SCRUM-189/g0/context-snapshot.yaml")]
        out = build_gate_evidence_artifact_map(evidence_candidates=cands, **_BASE)
        self.assertIn("EVIDENCE_G6_NOT_APPLICABLE", out["reason_codes"])

    def test_duplicate_conflict_blocks(self):
        cands = [
            _candidate("dup", "G0_CONTEXT", ".gwc/tasks/SCRUM-189/g0/context-snapshot.yaml",
                       digest="sha256:" + "a" * 64),
            _candidate("dup", "G0_CONTEXT", ".gwc/tasks/SCRUM-189/g0/context-snapshot.yaml",
                       digest="sha256:" + "b" * 64),
        ]
        out = build_gate_evidence_artifact_map(evidence_candidates=cands, **_BASE)
        self.assertIn("EVIDENCE_CONFLICT", out["reason_codes"])

    def test_invalid_candidate_shape_blocks(self):
        cands = [{"no": "evidence_key"}]
        out = build_gate_evidence_artifact_map(evidence_candidates=cands, **_BASE)
        self.assertIn("EVIDENCE_INPUT_INVALID", out["reason_codes"])


if __name__ == "__main__":
    unittest.main()
