from __future__ import annotations

import unittest

from tools.node_architect.g3_pass_decision import (
    G3_BLOCKED,
    G3_CHANGES_REQUIRED,
    G3_INCONCLUSIVE,
    G3_PASS,
    decide_g3_pass,
)

TASK = "SCRUM-219"
REPO = "nhatnguyenquang1838-coder/gwc"
BRANCH = "codex/scrum-256-validation-quality-closure-20260802"
BASE = "1" * 40
HEAD = "2" * 40
SCOPE = "sha256:" + "3" * 64
GRAPH = "scrum-256-route-v1"
POLICY = "sha256:" + "4" * 64


def package() -> dict:
    return {
        "task_id": TASK,
        "repository": REPO,
        "branch": BRANCH,
        "base_sha": BASE,
        "head_sha": HEAD,
        "scope_hash": SCOPE,
        "graph_revision": GRAPH,
        "policy_digest": POLICY,
        "idempotency_key": f"{TASK}:{HEAD}:g3",
        "evidence_quality_decision": {
            "status": "PASS",
            "reason_codes": ["EVIDENCE_ACCEPTED"],
            "task_id": TASK,
            "repository": REPO,
            "branch": BRANCH,
            "head_sha": HEAD,
            "scope_hash": SCOPE,
            "graph_revision": GRAPH,
            "quality_digest": "sha256:" + "5" * 64,
        },
        "validations": [
            {
                "name": "focused-tests",
                "status": "PASS",
                "head_sha": HEAD,
                "scope_hash": SCOPE,
                "digest": "sha256:" + "6" * 64,
            }
        ],
        "ready_for_review": {
            "eligible": True,
            "head_sha": HEAD,
            "scope_drift": False,
            "unresolved_threads": 0,
        },
        "findings": [],
    }


class G3PassDecisionM5Tests(unittest.TestCase):
    def test_passes_complete_package(self):
        result = decide_g3_pass(package())
        self.assertEqual(result["outcome"], G3_PASS)
        self.assertEqual(result["reason_codes"], ["G3_PASS"])
        self.assertFalse(result["merge_authority_granted"])

    def test_blocks_missing_quality(self):
        data = package()
        data.pop("evidence_quality_decision")
        result = decide_g3_pass(data)
        self.assertEqual(result["outcome"], G3_BLOCKED)
        self.assertIn("REQUIRED_EVIDENCE_MISSING", result["reason_codes"])

    def test_blocks_head_drift(self):
        data = package()
        data["validations"][0]["head_sha"] = "9" * 40
        result = decide_g3_pass(data)
        self.assertEqual(result["outcome"], G3_BLOCKED)
        self.assertIn("HEAD_DRIFT", result["reason_codes"])

    def test_inconclusive_pending_ci(self):
        data = package()
        data["validations"][0]["status"] = "PENDING"
        result = decide_g3_pass(data)
        self.assertEqual(result["outcome"], G3_INCONCLUSIVE)
        self.assertIn("CI_NOT_SUCCESS", result["reason_codes"])

    def test_changes_required_for_blocker(self):
        data = package()
        data["findings"] = [{"severity": "BLOCKER", "status": "OPEN"}]
        result = decide_g3_pass(data)
        self.assertEqual(result["outcome"], G3_CHANGES_REQUIRED)
        self.assertIn("UNRESOLVED_BLOCKER", result["reason_codes"])

    def test_changes_required_for_unresolved_side_effect(self):
        data = package()
        data["side_effects_unresolved"] = True
        result = decide_g3_pass(data)
        self.assertEqual(result["outcome"], G3_CHANGES_REQUIRED)
        self.assertIn("SIDE_EFFECT_UNRESOLVED", result["reason_codes"])

    def test_replay_is_deterministic(self):
        cache = {}
        first = decide_g3_pass(package(), replay_cache=cache)
        second = decide_g3_pass(package(), replay_cache=cache)
        self.assertEqual(first["decision_digest"], second["decision_digest"])
        self.assertTrue(second["replayed"])

    def test_same_key_different_input_blocks(self):
        cache = {}
        decide_g3_pass(package(), replay_cache=cache)
        changed = package()
        changed["ready_for_review"]["unresolved_threads"] = 1
        result = decide_g3_pass(changed, replay_cache=cache)
        self.assertEqual(result["outcome"], G3_BLOCKED)
        self.assertFalse(result["transition_effect_applied"])


if __name__ == "__main__":
    unittest.main()
