from __future__ import annotations

import unittest

from tools.node_architect.evidence_quality_check import (
    BLOCKED,
    PASS,
    check_evidence_quality,
)

REPO = "nhatnguyenquang1838-coder/gwc"
BASE = "1" * 40
HEAD = "2" * 40
SCOPE = "sha256:" + "3" * 64
BRANCH = "auto/scrum-338-na81-recert-20260814-r10"


def evidence(**overrides) -> dict:
    base = {
        "task_id": "SCRUM-338",
        "repository": REPO,
        "branch": BRANCH,
        "base_sha": BASE,
        "head_sha": HEAD,
        "scope_hash": SCOPE,
        "graph_revision": "scrum-288-route-v1",
        "idempotency_key": "scrum-338-quality-1",
        "pr_number": 999,
        "ci_evidence": {
            "status": "PASS",
            "reason_code": "CI_SUCCESS",
            "task_id": "SCRUM-338",
            "repository": REPO,
            "branch": BRANCH,
            "head_sha": HEAD,
            "scope_hash": SCOPE,
            "evidence_digest": "sha256:" + "4" * 64,
        },
        "review_receipt": {
            "schema_valid": True,
            "outcome": "PASS",
            "task_id": "SCRUM-338",
            "repository": REPO,
            "pr_number": 999,
            "head_sha": HEAD,
            "scope_hash": SCOPE,
            "reviewer_identity": "independent-reviewer",
            "reviewed_at": "2026-08-19T09:00:00Z",
            "source": "github-review",
            "access_mode": "read_only",
            "write_actions": [],
            "open_findings": 0,
            "findings": [],
        },
        "evaluated_at": "2026-08-19T09:05:00Z",
        "evidence_sources": ["github-actions", "github-review"],
    }
    base.update(overrides)
    return base


class EvidenceQualityCheckNa81F5Tests(unittest.TestCase):
    def test_accepts_complete_exact_head_evidence(self):
        result = check_evidence_quality(evidence())
        self.assertEqual(result["status"], PASS)
        self.assertEqual(result["reason_codes"], ["EVIDENCE_ACCEPTED"])
        self.assertFalse(result["merge_authority_granted"])
        self.assertFalse(result["deployment_authority_granted"])
        self.assertFalse(result["production_authority_granted"])

    def test_rejects_stale_evidence(self):
        value = evidence(max_age_seconds=60, evaluated_at="2026-08-19T09:05:00Z")
        # reviewed_at 09:00 -> evaluated_at 09:05 == 300s > 60s max_age -> STALE
        result = check_evidence_quality(value)
        self.assertEqual(result["status"], BLOCKED)
        self.assertIn("EVIDENCE_STALE", result["reason_codes"])

    def test_rejects_incomplete_evidence(self):
        value = evidence(ci_evidence=None)
        result = check_evidence_quality(value)
        self.assertEqual(result["status"], BLOCKED)
        self.assertIn("EVIDENCE_INCOMPLETE", result["reason_codes"])

    def test_rejects_mixed_head(self):
        value = evidence()
        value["review_receipt"]["head_sha"] = "9" * 40
        result = check_evidence_quality(value)
        self.assertEqual(result["status"], BLOCKED)
        self.assertIn("EVIDENCE_HEAD_MISMATCH", result["reason_codes"])

    def test_rejects_conflicting_terminal_conclusions(self):
        value = evidence(terminal_ci_conclusions=["CI_ACCEPTED", "CI_REJECTED"])
        result = check_evidence_quality(value)
        self.assertEqual(result["status"], BLOCKED)
        self.assertIn("EVIDENCE_CONTRADICTORY", result["reason_codes"])

    def test_rejects_projection_only_source(self):
        value = evidence()
        value["review_receipt"]["source"] = "jira"
        value["evidence_sources"] = ["jira", "slack"]
        result = check_evidence_quality(value)
        self.assertEqual(result["status"], BLOCKED)
        self.assertIn("EVIDENCE_PROJECTION_ONLY", result["reason_codes"])

    def test_replay_is_deterministic(self):
        cache: dict = {}
        first = check_evidence_quality(evidence(), replay_cache=cache)
        second = check_evidence_quality(evidence(), replay_cache=cache)
        self.assertEqual(first["quality_digest"], second["quality_digest"])
        self.assertTrue(second["replayed"])


if __name__ == "__main__":
    unittest.main()
