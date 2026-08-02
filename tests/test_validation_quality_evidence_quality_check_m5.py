from __future__ import annotations

import unittest

from tools.node_architect.evidence_quality_check import check_evidence_quality

TASK = "SCRUM-215"
REPO = "nhatnguyenquang1838-coder/gwc"
BRANCH = "codex/scrum-256-validation-quality-closure-20260802"
BASE = "1" * 40
HEAD = "2" * 40
SCOPE = "sha256:" + "3" * 64
GRAPH = "scrum-256-route-v1"


def package() -> dict:
    return {
        "task_id": TASK,
        "repository": REPO,
        "branch": BRANCH,
        "base_sha": BASE,
        "head_sha": HEAD,
        "scope_hash": SCOPE,
        "graph_revision": GRAPH,
        "idempotency_key": f"{TASK}:{HEAD}:quality",
        "pr_number": 176,
        "ci_evidence": {"status": "PASS", "reason_code": "CI_SUCCESS", "task_id": TASK, "repository": REPO, "branch": BRANCH, "head_sha": HEAD, "scope_hash": SCOPE, "evidence_digest": "sha256:" + "4" * 64},
        "review_receipt": {"schema_valid": True, "outcome": "PASS", "task_id": TASK, "repository": REPO, "pr_number": 176, "head_sha": HEAD, "scope_hash": SCOPE, "reviewer_identity": "independent-reviewer", "access_mode": "read_only", "write_actions": [], "open_findings": 0, "findings": [], "reviewed_at": "2026-08-02T09:00:00Z", "source": "github-review"},
        "evaluated_at": "2026-08-02T09:05:00Z",
        "max_age_seconds": 3600,
        "evidence_sources": ["github-actions", "github-review"],
        "terminal_ci_conclusions": ["success"],
    }


class EvidenceQualityCheckM5Tests(unittest.TestCase):
    def test_accepts_complete_exact_head_package(self):
        result = check_evidence_quality(package())
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["reason_codes"], ["EVIDENCE_ACCEPTED"])
        self.assertFalse(result["merge_authority_granted"])

    def test_blocks_missing_review_receipt(self):
        data = package(); data.pop("review_receipt")
        result = check_evidence_quality(data)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("EVIDENCE_INCOMPLETE", result["reason_codes"])

    def test_blocks_wrong_head(self):
        data = package(); data["review_receipt"]["head_sha"] = "9" * 40
        self.assertIn("EVIDENCE_HEAD_MISMATCH", check_evidence_quality(data)["reason_codes"])

    def test_blocks_projection_only(self):
        data = package(); data["review_receipt"]["source"] = "jira"; data["evidence_sources"] = ["jira", "slack"]
        self.assertIn("EVIDENCE_PROJECTION_ONLY", check_evidence_quality(data)["reason_codes"])

    def test_blocks_stale_review(self):
        data = package(); data["evaluated_at"] = "2026-08-03T09:05:00Z"
        self.assertIn("EVIDENCE_STALE", check_evidence_quality(data)["reason_codes"])

    def test_blocks_write_capable_review(self):
        data = package(); data["review_receipt"]["access_mode"] = "write"; data["review_receipt"]["write_actions"] = ["update_file"]
        self.assertIn("EVIDENCE_CONTRADICTORY", check_evidence_quality(data)["reason_codes"])

    def test_replay_is_deterministic(self):
        cache = {}; first = check_evidence_quality(package(), replay_cache=cache); second = check_evidence_quality(package(), replay_cache=cache)
        self.assertEqual(first["quality_digest"], second["quality_digest"]); self.assertTrue(second["replayed"])

    def test_same_key_different_input_fails_closed(self):
        cache = {}; check_evidence_quality(package(), replay_cache=cache)
        changed = package(); changed["evaluated_at"] = "2026-08-02T09:06:00Z"
        result = check_evidence_quality(changed, replay_cache=cache)
        self.assertEqual(result["reason_codes"], ["EVIDENCE_CONTRADICTORY"])


if __name__ == "__main__":
    unittest.main()
