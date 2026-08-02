from __future__ import annotations

import unittest

from tools.node_architect.evidence_quality_check import BLOCKED, PASS, check_evidence_quality

REPO = "nhatnguyenquang1838-coder/gwc"
BASE = "1" * 40
HEAD = "2" * 40
SCOPE = "sha256:" + "3" * 64
BRANCH = "codex/scrum-256-validation-quality-closure-r3-20260802"


def evidence() -> dict:
    return {
        "task_id": "SCRUM-215",
        "repository": REPO,
        "branch": BRANCH,
        "base_sha": BASE,
        "head_sha": HEAD,
        "scope_hash": SCOPE,
        "graph_revision": "scrum-256-route-v1",
        "idempotency_key": "scrum-215-quality-1",
        "pr_number": 178,
        "ci_evidence": {"status": "PASS", "reason_code": "CI_SUCCESS", "task_id": "SCRUM-215", "repository": REPO, "branch": BRANCH, "head_sha": HEAD, "scope_hash": SCOPE, "evidence_digest": "sha256:" + "4" * 64},
        "review_receipt": {"schema_valid": True, "outcome": "PASS", "task_id": "SCRUM-215", "repository": REPO, "pr_number": 178, "head_sha": HEAD, "scope_hash": SCOPE, "reviewer_identity": "independent-reviewer", "reviewed_at": "2026-08-02T09:00:00Z", "source": "github-review", "access_mode": "read_only", "write_actions": [], "open_findings": 0, "findings": []},
        "evaluated_at": "2026-08-02T09:05:00Z",
        "evidence_sources": ["github-actions", "github-review"],
    }


class EvidenceQualityCheckM5Tests(unittest.TestCase):
    def test_accepts_complete_exact_head_evidence(self):
        result = check_evidence_quality(evidence())
        self.assertEqual(result["status"], PASS)
        self.assertEqual(result["reason_codes"], ["EVIDENCE_ACCEPTED"])
        self.assertFalse(result["merge_authority_granted"])

    def test_rejects_head_mismatch(self):
        value = evidence(); value["review_receipt"]["head_sha"] = "9" * 40
        result = check_evidence_quality(value)
        self.assertEqual(result["status"], BLOCKED)
        self.assertIn("EVIDENCE_HEAD_MISMATCH", result["reason_codes"])

    def test_rejects_projection_only(self):
        value = evidence(); value["review_receipt"]["source"] = "jira"; value["evidence_sources"] = ["jira", "slack"]
        result = check_evidence_quality(value)
        self.assertEqual(result["status"], BLOCKED)
        self.assertIn("EVIDENCE_PROJECTION_ONLY", result["reason_codes"])

    def test_replay_is_deterministic(self):
        cache = {}
        first = check_evidence_quality(evidence(), replay_cache=cache)
        second = check_evidence_quality(evidence(), replay_cache=cache)
        self.assertEqual(first["quality_digest"], second["quality_digest"])
        self.assertTrue(second["replayed"])


if __name__ == "__main__":
    unittest.main()
