from __future__ import annotations

import unittest

from tools.node_architect.g3_pass_decision import G3_BLOCKED, G3_CHANGES_REQUIRED, G3_PASS, decide_g3_pass

REPO = "nhatnguyenquang1838-coder/gwc"
BASE = "1" * 40
HEAD = "2" * 40
SCOPE = "sha256:" + "3" * 64
BRANCH = "codex/scrum-256-validation-quality-closure-r3-20260802"


def evidence() -> dict:
    return {
        "task_id": "SCRUM-219",
        "repository": REPO,
        "branch": BRANCH,
        "base_sha": BASE,
        "head_sha": HEAD,
        "scope_hash": SCOPE,
        "graph_revision": "scrum-256-route-v1",
        "policy_digest": "sha256:" + "4" * 64,
        "idempotency_key": "scrum-219-g3-1",
        "evidence_quality_decision": {"status": "PASS", "reason_codes": ["EVIDENCE_ACCEPTED"], "task_id": "SCRUM-219", "repository": REPO, "branch": BRANCH, "head_sha": HEAD, "scope_hash": SCOPE, "graph_revision": "scrum-256-route-v1", "quality_digest": "sha256:" + "5" * 64},
        "validations": [{"name": "exact-route-canary", "status": "PASS", "head_sha": HEAD, "scope_hash": SCOPE, "digest": "sha256:" + "6" * 64}],
        "ready_for_review": {"eligible": True, "head_sha": HEAD, "scope_drift": False, "unresolved_threads": 0},
        "findings": [],
    }


class G3PassDecisionM5Tests(unittest.TestCase):
    def test_passes_complete_exact_head_package(self):
        result = decide_g3_pass(evidence())
        self.assertEqual(result["outcome"], G3_PASS)
        self.assertEqual(result["reason_codes"], ["G3_PASS"])
        self.assertFalse(result["merge_authority_granted"])

    def test_blocks_head_drift(self):
        value = evidence(); value["validations"][0]["head_sha"] = "9" * 40
        result = decide_g3_pass(value)
        self.assertEqual(result["outcome"], G3_BLOCKED)
        self.assertIn("HEAD_DRIFT", result["reason_codes"])

    def test_changes_required_for_blocker(self):
        value = evidence(); value["findings"] = [{"severity": "BLOCKER", "status": "OPEN"}]
        result = decide_g3_pass(value)
        self.assertEqual(result["outcome"], G3_CHANGES_REQUIRED)

    def test_replay_is_deterministic(self):
        cache = {}
        first = decide_g3_pass(evidence(), replay_cache=cache)
        second = decide_g3_pass(evidence(), replay_cache=cache)
        self.assertEqual(first["decision_digest"], second["decision_digest"])
        self.assertTrue(second["replayed"])


if __name__ == "__main__":
    unittest.main()
